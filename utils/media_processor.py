"""
Media Processor — CRF-based encoding for sharpest quality at smallest size.

Strategy:
  1. Stream copy if already H.264/AAC and fits Telegram limit
  2. CRF-based encode (sharpest quality, variable bitrate)
  3. If CRF output > 49MB → constrained bitrate fallback
  4. Split as last resort

CRF values (lower = sharper, larger file):
  <= 60s   → CRF 22  (short: max quality)
  <= 180s  → CRF 24  (medium: great quality)
  > 180s   → CRF 26  (long: good quality, controlled size)

Resolution rule:
  <= 120s  → keep original (max 1080p)
  > 120s   → 720p

Encoding:
  libx264 -preset veryfast -crf {value}
  aac 128k, MP4 + faststart, yuv420p

Rules:
  - Never 2-pass
  - Never slow preset
  - Stream copy whenever possible (fastest path)
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
AUDIO_KBPS      = 96                  # Audio bitrate — 96k is perfect for mobile
MIN_VIDEO_KBPS  = 400                 # Minimum video bitrate for constrained fallback
FFMPEG_THREADS  = "8"


# ─── CRF quality strategy ────────────────────────────────────────────────────

def _pick_crf(duration_s: float) -> int:
    """
    CRF value — higher = smaller file, lower quality.
    Tuned for Telegram mobile: sharp and small.
    CRF 28 on 720p looks great on phone screens.
    """
    if duration_s <= 60:
        return 28   # Short: sharp and small (~2-4MB for 30s)
    elif duration_s <= 180:
        return 30   # Medium: good quality, compact
    else:
        return 32   # Long: decent quality, very compact


def _target_height(duration_s: float, original_height: int) -> int:
    """
    Resolution: always cap at 720p.
    Telegram compresses 1080p anyway — 720p looks identical on mobile
    and downloads/encodes 2-3x faster.
    """
    return min(original_height, 720)


def _calc_constrained_kbps(target_mb: float, duration_s: float) -> int:
    """
    Constrained bitrate fallback — used only when CRF output exceeds 49MB.
    video_kbps = ((target_MB * 8192) / duration_s) - AUDIO_KBPS
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
    """True if video is already Telegram-compatible codec — can stream copy"""
    vcodec = (info.get("vcodec") or "").lower()
    acodec = (info.get("acodec") or "").lower()
    return (
        vcodec in ("h264", "avc", "avc1", "h265", "hevc") and
        acodec in ("aac", "mp4a", "mp4a.40.2", "opus", "vorbis")
    )


# ─── Core encode function (CRF-based) ─────────────────────────────────────────

async def adaptive_encode(
    input_path: Path,
    output_path: Path,
    force_height: Optional[int] = None,
    force_crf: Optional[int] = None,
) -> bool:
    """
    CRF-based adaptive encode — sharpest quality at smallest size.

    Steps:
      1. Get video info
      2. If already H.264/AAC and under Telegram limit → stream copy
      3. CRF encode with auto quality selection
      4. If output > 49MB → constrained bitrate fallback
    """
    info = await get_video_info(input_path)
    duration = info.get("duration") or 60.0
    orig_height = info.get("height") or 1080
    size = get_file_size(input_path)

    target_h = force_height or _target_height(duration, orig_height)
    crf = force_crf or _pick_crf(duration)

    # Stream copy if already compatible and under Telegram limit
    if _is_copy_compatible(info) and size <= TG_LIMIT_BYTES:
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

    logger.debug(f"adaptive_encode: {duration:.0f}s → {target_h}p CRF {crf}")

    # CRF-based encode — sharpest quality
    args = [
        "-y", "-i", str(input_path),
        "-vcodec", "libx264",
        "-preset", "ultrafast",
        "-crf", str(crf),
        "-vf", scale_filter,
        "-acodec", "aac",
        "-b:a", f"{AUDIO_KBPS}k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-threads", FFMPEG_THREADS,
        str(output_path),
    ]
    rc, err = await _run_ffmpeg(args)

    if rc == 0 and output_path.exists():
        out_size = get_file_size(output_path)
        if out_size <= TG_LIMIT_BYTES:
            logger.debug(f"CRF encode: {out_size/1024/1024:.1f}MB (CRF {crf})")
            return True
        # CRF output too large — constrained bitrate fallback
        logger.info(f"CRF output {out_size/1024/1024:.1f}MB > 49MB, using constrained bitrate")
        return await _constrained_encode(input_path, output_path, duration, target_h)

    if rc != 0:
        logger.warning(f"adaptive_encode CRF failed: {err[:200]}")
    return rc == 0


async def _constrained_encode(
    input_path: Path,
    output_path: Path,
    duration: float,
    target_h: int,
) -> bool:
    """
    Constrained bitrate fallback — guarantees output fits Telegram limit.
    Used only when CRF output exceeds 49MB.
    """
    target_mb = 45.0  # Target 45MB to fit under 49MB limit
    video_kbps = _calc_constrained_kbps(target_mb, duration)
    scale_filter = f"scale=-2:{target_h}:flags=lanczos"

    logger.debug(f"constrained_encode: {duration:.0f}s → {target_h}p @ {video_kbps}kbps")

    args = [
        "-y", "-i", str(input_path),
        "-vcodec", "libx264",
        "-preset", "ultrafast",
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
        logger.warning(f"constrained_encode failed: {err[:200]}")
    return rc == 0


# ─── Instagram smart encode ───────────────────────────────────────────────────

async def instagram_smart_encode(input_path: Path, output_path: Path) -> bool:
    """
    Instagram: stream copy if H.264/AAC and small, else CRF encode.
    Preserve native FPS. Max quality for short Instagram content.
    """
    info = await get_video_info(input_path)
    duration = info.get("duration") or 30.0
    size = get_file_size(input_path)

    # Stream copy if already compatible and fits
    if _is_copy_compatible(info) and size <= TG_LIMIT_BYTES:
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

    # CRF encode preserving FPS
    fps = info.get("fps") or 30.0
    fps = min(fps, 60.0)
    orig_height = info.get("height") or 1080
    target_h = _target_height(duration, orig_height)
    crf = _pick_crf(duration)

    logger.debug(f"Instagram: CRF {crf} {target_h}p fps={fps:.1f}")
    args = [
        "-y", "-i", str(input_path),
        "-vcodec", "libx264",
        "-preset", "ultrafast",
        "-crf", str(crf),
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
    YouTube Shorts: stream copy if compatible, else CRF encode.
    Short content → keep 1080p, CRF 22 (max quality).
    """
    info = await get_video_info(input_path)
    size = get_file_size(input_path)

    if _is_copy_compatible(info) and size <= TG_LIMIT_BYTES:
        args = [
            "-y", "-i", str(input_path),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ]
        rc, _ = await _run_ffmpeg(args)
        if rc == 0:
            return True

    # Shorts are short → use best quality CRF 22
    return await adaptive_encode(input_path, output_path, force_crf=22)


# ─── Ensure fits Telegram ─────────────────────────────────────────────────────

async def ensure_fits_telegram(
    video_path: Path,
    tmp_dir: Path,
    limit_bytes: int = TG_LIMIT_BYTES,
) -> List[Path]:
    """
    Ensure video fits Telegram limits.
    1. If fits → ensure MP4 faststart
    2. CRF adaptive encode
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

    logger.info(f"File {size/1024/1024:.1f}MB exceeds limit, CRF adaptive encode")

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
    return await adaptive_encode(input_path, output_path, force_height=target_height, force_crf=crf)


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
