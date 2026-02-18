"""
Media processor — FFmpeg re-encode, adaptive compression, smart splitting.
Handles Telegram file size limits automatically and silently.
"""
import asyncio
import os
import math
from pathlib import Path
from typing import List, Optional, Tuple
from utils.logger import logger
from core.config import config

# ─── Constants ────────────────────────────────────────────────────────────────
TG_LIMIT_BYTES = 49 * 1024 * 1024   # 49 MB safety margin
SPLIT_CHUNK_MB = 45                  # Each split part target size

# ─── FFmpeg helpers ───────────────────────────────────────────────────────────

async def _run_ffmpeg(args: List[str], timeout: int = None) -> Tuple[int, str]:
    """
    Run FFmpeg command asynchronously.
    Returns (returncode, stderr_output).
    """
    timeout = timeout or config.FFMPEG_TIMEOUT
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode, stderr.decode(errors="replace")
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            logger.warning(f"FFmpeg timed out after {timeout}s")
            return -1, "timeout"
    except FileNotFoundError:
        logger.error("FFmpeg not found — install ffmpeg")
        return -1, "ffmpeg not found"
    except Exception as e:
        logger.error(f"FFmpeg error: {e}")
        return -1, str(e)

def get_file_size(path: Path) -> int:
    """Get file size in bytes"""
    try:
        return path.stat().st_size
    except Exception:
        return 0

async def get_video_duration(path: Path) -> Optional[float]:
    """Get video duration in seconds using ffprobe"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        import json
        data = json.loads(stdout.decode())
        return float(data["format"]["duration"])
    except Exception:
        return None

# ─── Re-encode for quality + size ────────────────────────────────────────────

async def reencode_video(
    input_path: Path,
    output_path: Path,
    target_height: int = 1080,
    crf: int = 23
) -> bool:
    """
    Re-encode video with H.264 for Telegram compatibility.
    Scales to target_height, uses CRF for quality control.
    Returns True on success.
    """
    args = [
        "-y", "-i", str(input_path),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", str(crf),
        "-vf", f"scale=-2:{target_height}:flags=lanczos",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        str(output_path)
    ]
    rc, err = await _run_ffmpeg(args)
    if rc != 0:
        logger.warning(f"Re-encode failed (crf={crf}): {err[:200]}")
    return rc == 0

async def reencode_shorts(input_path: Path, output_path: Path) -> bool:
    """
    Re-encode YouTube Shorts for high visual quality + small file size.
    Targets 1080p with efficient encoding.
    """
    args = [
        "-y", "-i", str(input_path),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "22",
        "-vf", "scale=-2:1080:flags=lanczos",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        str(output_path)
    ]
    rc, err = await _run_ffmpeg(args)
    return rc == 0

# ─── Adaptive compression ─────────────────────────────────────────────────────

async def compress_to_limit(
    input_path: Path,
    output_path: Path,
    limit_bytes: int = TG_LIMIT_BYTES
) -> bool:
    """
    Adaptively compress video to fit within Telegram limit.
    Tries progressively higher CRF values until file fits.
    Returns True if compression succeeded.
    """
    size = get_file_size(input_path)
    if size <= limit_bytes:
        # Already fits — just copy
        import shutil
        shutil.copy2(str(input_path), str(output_path))
        return True
    
    # Calculate required bitrate
    duration = await get_video_duration(input_path)
    if not duration or duration <= 0:
        duration = 60  # fallback
    
    target_size_bits = limit_bytes * 8
    target_bitrate_kbps = int((target_size_bits / duration) / 1000) - 128  # reserve 128k for audio
    target_bitrate_kbps = max(target_bitrate_kbps, 300)  # minimum 300k video
    
    logger.info(f"Compressing {size/1024/1024:.1f}MB → target {limit_bytes/1024/1024:.0f}MB "
                f"(bitrate: {target_bitrate_kbps}k, duration: {duration:.0f}s)")
    
    args = [
        "-y", "-i", str(input_path),
        "-c:v", "libx264",
        "-preset", "fast",
        "-b:v", f"{target_bitrate_kbps}k",
        "-maxrate", f"{int(target_bitrate_kbps * 1.5)}k",
        "-bufsize", f"{target_bitrate_kbps * 2}k",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        str(output_path)
    ]
    rc, err = await _run_ffmpeg(args)
    if rc != 0:
        logger.warning(f"Compression failed: {err[:200]}")
        return False
    
    result_size = get_file_size(output_path)
    logger.info(f"Compressed to {result_size/1024/1024:.1f}MB")
    return result_size <= limit_bytes

# ─── Smart splitting ──────────────────────────────────────────────────────────

async def split_video(
    input_path: Path,
    output_dir: Path,
    chunk_mb: int = SPLIT_CHUNK_MB
) -> List[Path]:
    """
    Split video into chunks that fit Telegram limits.
    Returns list of part paths.
    """
    duration = await get_video_duration(input_path)
    if not duration:
        return []
    
    size = get_file_size(input_path)
    size_mb = size / 1024 / 1024
    
    num_parts = math.ceil(size_mb / chunk_mb)
    part_duration = duration / num_parts
    
    logger.info(f"Splitting {size_mb:.1f}MB video into {num_parts} parts ({part_duration:.0f}s each)")
    
    parts = []
    stem = input_path.stem
    ext = input_path.suffix
    
    for i in range(num_parts):
        start = i * part_duration
        part_path = output_dir / f"{stem}_part{i+1}{ext}"
        
        args = [
            "-y",
            "-ss", str(start),
            "-i", str(input_path),
            "-t", str(part_duration),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            str(part_path)
        ]
        rc, err = await _run_ffmpeg(args)
        if rc == 0 and part_path.exists():
            parts.append(part_path)
        else:
            logger.warning(f"Split part {i+1} failed: {err[:100]}")
    
    return parts

# ─── Main entry point ─────────────────────────────────────────────────────────

async def ensure_fits_telegram(
    video_path: Path,
    tmp_dir: Path,
    limit_bytes: int = TG_LIMIT_BYTES
) -> List[Path]:
    """
    Ensure video fits Telegram limits.
    Strategy:
      1. If fits → return as-is
      2. Try smart re-encode with compression
      3. If still too large → split into parts
    
    Returns list of paths to send (1 file or multiple parts).
    """
    size = get_file_size(video_path)
    
    if size <= limit_bytes:
        return [video_path]
    
    logger.info(f"File {size/1024/1024:.1f}MB exceeds limit, attempting compression")
    
    # Step 1: Try compression
    compressed = tmp_dir / f"compressed_{video_path.name}"
    success = await compress_to_limit(video_path, compressed, limit_bytes)
    
    if success and get_file_size(compressed) <= limit_bytes:
        logger.info("Compression successful")
        return [compressed]
    
    # Step 2: Split
    logger.info("Compression insufficient, splitting video")
    parts = await split_video(video_path, tmp_dir)
    
    if parts:
        return parts
    
    # Fallback: return original (will fail at send, but we tried)
    logger.warning("Could not compress or split — returning original")
    return [video_path]

async def extract_audio_from_video(
    video_path: Path,
    output_path: Path,
    bitrate: str = "320k"
) -> bool:
    """Extract audio track from video as MP3"""
    args = [
        "-y", "-i", str(video_path),
        "-vn",
        "-c:a", "libmp3lame",
        "-b:a", bitrate,
        "-q:a", "0",
        str(output_path)
    ]
    rc, err = await _run_ffmpeg(args)
    return rc == 0
