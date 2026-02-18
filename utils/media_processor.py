"""
Media processor — FFmpeg re-encode, adaptive compression, smart splitting.

Strategy:
  - Short videos (< 60s): H.264 fast preset (speed priority)
  - Long videos that are too large: VP9 compression, fallback to H.264 if VP9 fails
  - Smart 1080p: keep 1080p if file fits, apply adaptive CRF if too large
  - Instagram: stream copy if already H.264/AAC, re-encode only if needed
  - All output: MP4 container with -movflags +faststart for Telegram preview
"""
import asyncio
import json
import math
import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from utils.logger import logger
from core.config import config

# ─── Constants ────────────────────────────────────────────────────────────────
TG_LIMIT_BYTES = 49 * 1024 * 1024   # 49 MB safety margin
SPLIT_CHUNK_MB = 45                  # Each split part target size
SHORT_VIDEO_THRESHOLD_S = 60         # Videos shorter than this use H.264 fast

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
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode, stderr.decode(errors="replace")
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.communicate()
            except Exception:
                pass
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

async def get_video_info(path: Path) -> dict:
    """
    Get video metadata (duration, codec, width, height, fps) using ffprobe.
    Returns dict with keys: duration, vcodec, acodec, width, height, fps.
    """
    result = {
        "duration": None,
        "vcodec": None,
        "acodec": None,
        "width": None,
        "height": None,
        "fps": None,
    }
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        data = json.loads(stdout.decode())

        fmt = data.get("format", {})
        result["duration"] = float(fmt.get("duration", 0)) or None

        for stream in data.get("streams", []):
            codec_type = stream.get("codec_type", "")
            if codec_type == "video" and result["vcodec"] is None:
                result["vcodec"] = stream.get("codec_name")
                result["width"] = stream.get("width")
                result["height"] = stream.get("height")
                # fps as fraction string e.g. "30/1"
                fps_str = stream.get("r_frame_rate", "")
                if fps_str and "/" in fps_str:
                    num, den = fps_str.split("/")
                    try:
                        result["fps"] = float(num) / float(den) if float(den) else None
                    except Exception:
                        pass
            elif codec_type == "audio" and result["acodec"] is None:
                result["acodec"] = stream.get("codec_name")

    except Exception as e:
        logger.debug(f"ffprobe failed: {e}")

    return result

async def get_video_duration(path: Path) -> Optional[float]:
    """Get video duration in seconds"""
    info = await get_video_info(path)
    return info.get("duration")

# ─── Instagram stream-copy ────────────────────────────────────────────────────

async def instagram_smart_encode(input_path: Path, output_path: Path) -> bool:
    """
    For Instagram content:
    - If already H.264 video + AAC audio → stream copy (fast, no quality loss)
    - Otherwise → re-encode with H.264 fast preset
    Always outputs MP4 with faststart for Telegram preview.
    """
    info = await get_video_info(input_path)
    vcodec = (info.get("vcodec") or "").lower()
    acodec = (info.get("acodec") or "").lower()

    can_copy = (
        vcodec in ("h264", "avc", "avc1") and
        acodec in ("aac", "mp4a")
    )

    if can_copy:
        logger.debug(f"Instagram: stream copy ({vcodec}/{acodec})")
        args = [
            "-y", "-i", str(input_path),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ]
    else:
        logger.debug(f"Instagram: re-encode ({vcodec}/{acodec})")
        # Preserve original FPS and resolution
        fps = info.get("fps") or 30
        fps = min(fps, 60)  # cap at 60fps
        args = [
            "-y", "-i", str(input_path),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-vf", f"fps={fps:.3f}",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]

    rc, err = await _run_ffmpeg(args)
    if rc != 0:
        logger.warning(f"Instagram encode failed: {err[:200]}")
    return rc == 0

# ─── Re-encode for quality + size ────────────────────────────────────────────

async def reencode_video(
    input_path: Path,
    output_path: Path,
    target_height: int = 1080,
    crf: int = 23,
) -> bool:
    """
    Re-encode video with H.264 for Telegram compatibility.
    Scales to target_height (keeping aspect ratio), uses CRF for quality.
    Outputs MP4 with faststart.
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
        str(output_path),
    ]
    rc, err = await _run_ffmpeg(args)
    if rc != 0:
        logger.warning(f"Re-encode failed (crf={crf}): {err[:200]}")
    return rc == 0

async def reencode_shorts(input_path: Path, output_path: Path) -> bool:
    """
    Re-encode YouTube Shorts for high visual quality + small file size.
    Targets 1080p with H.264 medium preset (good quality/size balance).
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
        str(output_path),
    ]
    rc, err = await _run_ffmpeg(args)
    return rc == 0

# ─── Smart 1080p with adaptive CRF ───────────────────────────────────────────

async def smart_encode_for_telegram(
    input_path: Path,
    output_path: Path,
    limit_bytes: int = TG_LIMIT_BYTES,
) -> bool:
    """
    Encode video for Telegram with smart 1080p handling:
    1. Get video info (duration, codec, size)
    2. If short (< 60s): H.264 fast preset, CRF 22
    3. If long and large: try VP9 compression; fallback to H.264 with adaptive CRF
    4. Always output MP4 with faststart
    5. Never force 720p — keep 1080p if it fits
    """
    info = await get_video_info(input_path)
    duration = info.get("duration") or 60
    size = get_file_size(input_path)
    height = info.get("height") or 1080

    # Determine target height: keep original if ≤ 1080, else cap at 1080
    target_height = min(height, 1080)

    # Short video: H.264 fast (speed priority)
    if duration < SHORT_VIDEO_THRESHOLD_S:
        logger.debug(f"Smart encode: short video ({duration:.0f}s), H.264 fast")
        args = [
            "-y", "-i", str(input_path),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-vf", f"scale=-2:{target_height}:flags=lanczos",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        rc, err = await _run_ffmpeg(args)
        if rc == 0:
            return True
        logger.warning(f"H.264 fast encode failed: {err[:100]}")

    # Long video: try VP9 first if file is large
    if size > limit_bytes and duration >= SHORT_VIDEO_THRESHOLD_S:
        logger.debug(f"Smart encode: long video ({duration:.0f}s, {size/1024/1024:.1f}MB), trying VP9")
        vp9_out = output_path.parent / f"vp9_{output_path.name}"
        # VP9 two-pass would be ideal but slow; use CQ mode
        args_vp9 = [
            "-y", "-i", str(input_path),
            "-c:v", "libvpx-vp9",
            "-crf", "33",
            "-b:v", "0",
            "-vf", f"scale=-2:{target_height}:flags=lanczos",
            "-c:a", "libopus",
            "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            str(vp9_out),
        ]
        rc_vp9, err_vp9 = await _run_ffmpeg(args_vp9, timeout=config.FFMPEG_TIMEOUT)

        if rc_vp9 == 0 and vp9_out.exists():
            vp9_size = get_file_size(vp9_out)
            if vp9_size <= limit_bytes:
                # VP9 fits — but Telegram needs MP4 for preview
                # Re-mux to MP4 (stream copy if possible, else re-encode audio)
                args_mux = [
                    "-y", "-i", str(vp9_out),
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(output_path),
                ]
                rc_mux, _ = await _run_ffmpeg(args_mux)
                try:
                    vp9_out.unlink(missing_ok=True)
                except Exception:
                    pass
                if rc_mux == 0:
                    logger.debug(f"VP9 encode succeeded: {vp9_size/1024/1024:.1f}MB")
                    return True
            else:
                logger.debug(f"VP9 still too large ({vp9_size/1024/1024:.1f}MB), falling back to H.264")
            try:
                vp9_out.unlink(missing_ok=True)
            except Exception:
                pass
        else:
            logger.debug(f"VP9 encode failed: {err_vp9[:100]}")

    # Fallback: H.264 with adaptive CRF based on target bitrate
    logger.debug(f"Smart encode: H.264 adaptive CRF fallback")
    target_size_bits = limit_bytes * 8
    target_bitrate_kbps = max(300, int((target_size_bits / max(duration, 1)) / 1000) - 192)

    args_h264 = [
        "-y", "-i", str(input_path),
        "-c:v", "libx264",
        "-preset", "fast",
        "-b:v", f"{target_bitrate_kbps}k",
        "-maxrate", f"{int(target_bitrate_kbps * 1.5)}k",
        "-bufsize", f"{target_bitrate_kbps * 2}k",
        "-vf", f"scale=-2:{target_height}:flags=lanczos",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    rc, err = await _run_ffmpeg(args_h264)
    if rc != 0:
        logger.warning(f"H.264 adaptive encode failed: {err[:200]}")
    return rc == 0

# ─── Adaptive compression ─────────────────────────────────────────────────────

async def compress_to_limit(
    input_path: Path,
    output_path: Path,
    limit_bytes: int = TG_LIMIT_BYTES,
) -> bool:
    """
    Adaptively compress video to fit within Telegram limit.
    Uses smart_encode_for_telegram for best results.
    """
    size = get_file_size(input_path)
    if size <= limit_bytes:
        shutil.copy2(str(input_path), str(output_path))
        return True

    return await smart_encode_for_telegram(input_path, output_path, limit_bytes)

# ─── Smart splitting ──────────────────────────────────────────────────────────

async def split_video(
    input_path: Path,
    output_dir: Path,
    chunk_mb: int = SPLIT_CHUNK_MB,
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
            "-movflags", "+faststart",
            str(part_path),
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
    limit_bytes: int = TG_LIMIT_BYTES,
) -> List[Path]:
    """
    Ensure video fits Telegram limits.
    Strategy:
      1. If fits → ensure MP4 with faststart (re-mux if needed)
      2. Try smart encode (VP9 or H.264 adaptive)
      3. If still too large → split into parts

    Returns list of paths to send (1 file or multiple parts).
    """
    size = get_file_size(video_path)

    if size <= limit_bytes:
        # Ensure MP4 with faststart for Telegram preview
        if video_path.suffix.lower() not in (".mp4",):
            remuxed = tmp_dir / f"remuxed_{video_path.stem}.mp4"
            args = [
                "-y", "-i", str(video_path),
                "-c", "copy",
                "-movflags", "+faststart",
                str(remuxed),
            ]
            rc, _ = await _run_ffmpeg(args)
            if rc == 0 and remuxed.exists():
                return [remuxed]
        return [video_path]

    logger.info(f"File {size/1024/1024:.1f}MB exceeds limit, attempting smart encode")

    # Step 1: Smart encode
    encoded = tmp_dir / f"encoded_{video_path.stem}.mp4"
    success = await smart_encode_for_telegram(video_path, encoded, limit_bytes)

    if success and encoded.exists() and get_file_size(encoded) <= limit_bytes:
        logger.info(f"Smart encode succeeded: {get_file_size(encoded)/1024/1024:.1f}MB")
        return [encoded]

    # Step 2: Split
    logger.info("Smart encode insufficient, splitting video")
    parts = await split_video(video_path, tmp_dir)

    if parts:
        return parts

    # Fallback: return original
    logger.warning("Could not compress or split — returning original")
    return [video_path]

async def extract_audio_from_video(
    video_path: Path,
    output_path: Path,
    bitrate: str = "320k",
) -> bool:
    """Extract audio track from video as MP3"""
    args = [
        "-y", "-i", str(video_path),
        "-vn",
        "-c:a", "libmp3lame",
        "-b:a", bitrate,
        "-q:a", "0",
        str(output_path),
    ]
    rc, err = await _run_ffmpeg(args)
    return rc == 0
