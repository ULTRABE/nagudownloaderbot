"""
Media Processor — Adaptive re-encode with aggressive target-size rules.

Resolution rule:
  duration <= 120s  →  keep original (allow 1080p)
  duration >  120s  →  downscale to 720p

Target size rule:
  <= 30s   →  5 MB
  <= 120s  →  7 MB
  <= 300s  →  10 MB
  > 300s   →  14 MB

Bitrate formula:
  video_kbps = ((target_MB * 8192) / duration_s) - 128
  clamp minimum to 600 kbps

Encode command (FAST MODE):
  ffmpeg -vcodec libx264 -preset veryfast -b:v {kbps}k
         -maxrate {kbps}k -bufsize {kbps*2}k
         -acodec aac -b:a 128k -movflags +faststart -threads 6

Rules:
  - Never 2-pass
  - Never slow preset
  - Never VP9 in speed mode
  - Stream copy if already small + H.264/AAC
  - Always MP4 + faststart for Telegram preview
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
TG_LIMIT_BYTES  = 49 * 1024 * 1024   # 49 MB safety margin
SPLIT_CHUNK_MB  = 45                  # Each split part target
MIN_VIDEO_KBPS  = 600                 # Minimum video bitrate
AUDIO_KBPS      = 128                 # Audio bitrate (kbps)
FFMPEG_THREADS  = "6"


# ─── Target size lookup ───────────────────────────────────────────────────────

def _target_size_mb(duration_s: float) -> float:
    """Return target file size in MB based on duration"""
    if duration_s <= 30:
        return 5.0
    elif duration_s <= 120:
        return 7.0
    elif duration_s <= 300:
        return 10.0
    else:
        return 14.0


def _target_height(duration_s: float, original_height: int) -> int:
    """
    Resolution rule:
      <= 120s  →  keep original (max 1080)
      >  120s  →  720p
    Never upscale.
    """
    if duration_s <= 120:
        return min(original_height, 1080)
    else:
        return min(original_height, 720)


def _calc_video_kbps(target_mb: float, duration_s: float) -> int:
    """
    video_kbps = ((target_MB * 8192) / duration_s) - AUDIO_KBPS
    Clamp to MIN_VIDEO_KBPS.
    """
    if duration_s <= 0:
        return MIN_VIDEO_KBPS
    raw = int((target_mb * 8192) / duration_s) - AUDIO_KBPS
    return max(MIN_VIDEO_KBPS, raw)


# ─── FFmpeg runner ────────────────────────────────────────────────────────────

async def _run_ffmpeg(args: List[str], timeout: int = None) -> Tuple[int, str]:
    """
    Run FFmpeg asynchronously.
    Returns (returncode, stderr_text).
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


# ─── File utilities ───────────────────────────────────────────────────────────

def get_file_size(path: Path) -> int:
    """File size in bytes"""
    try:
        return path.stat().st_size
    except Exception:
        return 0


async def get_video_info(path: Path) -> dict:
    """
    Get video metadata via ffprobe.
    Returns: {duration, vcodec, acodec, width, height, fps}
    """
    result = {
        "duration": None, "vcodec": None, "acodec": None,
        "width": None, "height": None, "fps": None,
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
            ctype = stream.get("codec_type", "")
            if ctype == "video" and result["vcodec"] is None:
                result["vcodec"] = stream.get("codec_name")
                result["width"]  = stream.get("width")
                result["height"] = stream.get("height")
                fps_str = stream.get("r_frame_rate", "")
                if fps_str and "/" in fps_str:
                    num, den = fps_str.split("/")
                    try:
                        result["fps"] = float(num) / float(den) if float(den) else None
                    except Exception:
                        pass
            elif ctype == "audio" and result["acodec"] is None:
                result["acodec"] = stream.get("codec_name")

    except Exception as e:
        logger.debug(f"ffprobe failed: {e}")

    return result


async def get_video_duration(path: Path) -> Optional[float]:
    """Get video duration in seconds"""
    info = await get_video_info(path)
    return info.get("duration")


# ─── Stream copy check ────────────────────────────────────────────────────────

def _is_copy_compatible(info: dict) -> bool:
    """True if video is already H.264/AAC — can stream copy"""
    vcodec = (info.get("vcodec") or "").lower()
    acodec = (info.get("acodec") or "").lower()
    return (
        vcodec in ("h264", "avc", "avc1") and
        acodec in ("aac", "mp4a", "mp4a.40.2")
    )


# ─── Core encode function ─────────────────────────────────────────────────────

async def adaptive_encode(
    input_path: Path,
    output_path: Path,
    force_height: Optional[int] = None,
    force_kbps: Optional[int] = None,
) -> bool:
    """
    Adaptive encode using veryfast preset + calculated bitrate.

    Steps:
      1. Get video info
      2. Calculate target size, height, bitrate
      3. If already small + H.264/AAC → stream copy
      4. Else → encode with veryfast + calculated bitrate
    """
    info = await get_video_info(input_path)
    duration = info.get("duration") or 60.0
    orig_height = info.get("height") or 1080
    size = get_file_size(input_path)

    target_mb   = _target_size_mb(duration)
    target_h    = force_height or _target_height(duration, orig_height)
    video_kbps  = force_kbps or _calc_video_kbps(target_mb, duration)
    target_bytes = int(target_mb * 1024 * 1024)

    # Stream copy if already compatible and small enough
    if _is_copy_compatible(info) and size <= target_bytes:
        logger.debug(f"adaptive_encode: stream copy ({size/1024/1024:.1f}MB)")
        args = [
            "-y", "-i", str(input_path),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ]
        rc, err = await _run_ffmpeg(args)
        if rc == 0:
            return True
        logger.debug(f"Stream copy failed, falling back to encode: {err[:80]}")

    # Scale filter — never upscale
    scale_filter = f"scale=-2:{target_h}:flags=lanczos"

    logger.debug(
        f"adaptive_encode: {duration:.0f}s → {target_h}p "
        f"@ {video_kbps}kbps (target {target_mb}MB)"
    )

    args = [
        "-y", "-i", str(input_path),
        "-vcodec", "libx264",
        "-preset", "veryfast",
        "-b:v", f"{video_kbps}k",
        "-maxrate", f"{video_kbps}k",
        "-bufsize", f"{video_kbps * 2}k",
        "-vf", scale_filter,
        "-acodec", "aac",
        "-b:a", f"{AUDIO_KBPS}k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-threads", FFMPEG_THREADS,
        str(output_path),
    ]
    rc, err = await _run_ffmpeg(args)
    if rc != 0:
        logger.warning(f"adaptive_encode failed: {err[:200]}")
    return rc == 0


# ─── Instagram smart encode ───────────────────────────────────────────────────

async def instagram_smart_encode(input_path: Path, output_path: Path) -> bool:
    """
    Instagram: stream copy if H.264/AAC, else adaptive encode.
    Preserve native FPS. Target 4–6MB for short content.
    """
    info = await get_video_info(input_path)
    duration = info.get("duration") or 30.0
    size = get_file_size(input_path)
    target_bytes = int(_target_size_mb(duration) * 1024 * 1024)

    if _is_copy_compatible(info) and size <= target_bytes:
        logger.debug("Instagram: stream copy")
        args = [
            "-y", "-i", str(input_path),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ]
        rc, _ = await _run_ffmpeg(args)
        if rc == 0:
            return True

    # Re-encode preserving FPS
    fps = info.get("fps") or 30.0
    fps = min(fps, 60.0)
    orig_height = info.get("height") or 1080
    target_h = _target_height(duration, orig_height)
    video_kbps = _calc_video_kbps(_target_size_mb(duration), duration)

    logger.debug(f"Instagram: re-encode {target_h}p @ {video_kbps}kbps fps={fps:.1f}")
    args = [
        "-y", "-i", str(input_path),
        "-vcodec", "libx264",
        "-preset", "veryfast",
        "-b:v", f"{video_kbps}k",
        "-maxrate", f"{video_kbps}k",
        "-bufsize", f"{video_kbps * 2}k",
        "-vf", f"scale=-2:{target_h}:flags=lanczos,fps={fps:.3f}",
        "-acodec", "aac",
        "-b:a", f"{AUDIO_KBPS}k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-threads", FFMPEG_THREADS,
        str(output_path),
    ]
    rc, err = await _run_ffmpeg(args)
    if rc != 0:
        logger.warning(f"Instagram encode failed: {err[:200]}")
    return rc == 0


# ─── Shorts re-encode ─────────────────────────────────────────────────────────

async def reencode_shorts(input_path: Path, output_path: Path) -> bool:
    """
    YouTube Shorts: stream copy if compatible, else veryfast encode.
    Short content → keep 1080p.
    """
    info = await get_video_info(input_path)
    duration = info.get("duration") or 30.0
    size = get_file_size(input_path)
    target_bytes = int(_target_size_mb(duration) * 1024 * 1024)

    if _is_copy_compatible(info) and size <= target_bytes:
        args = [
            "-y", "-i", str(input_path),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ]
        rc, _ = await _run_ffmpeg(args)
        if rc == 0:
            return True

    return await adaptive_encode(input_path, output_path)


# ─── Ensure fits Telegram ─────────────────────────────────────────────────────

async def ensure_fits_telegram(
    video_path: Path,
    tmp_dir: Path,
    limit_bytes: int = TG_LIMIT_BYTES,
) -> List[Path]:
    """
    Ensure video fits Telegram limits.
    1. If fits → ensure MP4 faststart
    2. Adaptive encode
    3. Split if still too large
    Returns list of paths to send.
    """
    size = get_file_size(video_path)

    if size <= limit_bytes:
        # Ensure MP4 + faststart
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

    logger.info(f"File {size/1024/1024:.1f}MB exceeds limit, adaptive encode")

    encoded = tmp_dir / f"enc_{video_path.stem}.mp4"
    ok = await adaptive_encode(video_path, encoded)

    if ok and encoded.exists() and get_file_size(encoded) <= limit_bytes:
        logger.info(f"Encode succeeded: {get_file_size(encoded)/1024/1024:.1f}MB")
        return [encoded]

    # Split as last resort
    logger.info("Encode insufficient, splitting")
    parts = await split_video(video_path, tmp_dir)
    if parts:
        return parts

    logger.warning("Could not compress or split — returning original")
    return [video_path]


# ─── Video splitting ──────────────────────────────────────────────────────────

async def split_video(
    input_path: Path,
    output_dir: Path,
    chunk_mb: int = SPLIT_CHUNK_MB,
) -> List[Path]:
    """Split video into Telegram-safe chunks"""
    duration = await get_video_duration(input_path)
    if not duration:
        return []

    size = get_file_size(input_path)
    size_mb = size / 1024 / 1024
    num_parts = math.ceil(size_mb / chunk_mb)
    part_duration = duration / num_parts

    logger.info(f"Splitting {size_mb:.1f}MB into {num_parts} parts")

    parts = []
    stem = input_path.stem

    for i in range(num_parts):
        start = i * part_duration
        part_path = output_dir / f"{stem}_part{i+1}.mp4"
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


# ─── Audio extraction ─────────────────────────────────────────────────────────

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


# ─── Legacy compat ────────────────────────────────────────────────────────────

async def reencode_video(
    input_path: Path,
    output_path: Path,
    target_height: int = 1080,
    crf: int = 23,
) -> bool:
    """Legacy compat — delegates to adaptive_encode"""
    return await adaptive_encode(input_path, output_path, force_height=target_height)


async def smart_encode_for_telegram(
    input_path: Path,
    output_path: Path,
    limit_bytes: int = TG_LIMIT_BYTES,
) -> bool:
    """Legacy compat — delegates to adaptive_encode"""
    return await adaptive_encode(input_path, output_path)


async def compress_to_limit(
    input_path: Path,
    output_path: Path,
    limit_bytes: int = TG_LIMIT_BYTES,
) -> bool:
    """Legacy compat"""
    size = get_file_size(input_path)
    if size <= limit_bytes:
        shutil.copy2(str(input_path), str(output_path))
        return True
    return await adaptive_encode(input_path, output_path)
