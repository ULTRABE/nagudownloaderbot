"""
Pinterest Downloader — Silent delivery with carousel + private pin support.

Flow:
  1. Resolve pin.it short URLs (HEAD request)
  2. Validate URL
  3. Send sticker (if enabled)
  4. Download silently (no progress messages)
  5. Delete sticker after delivery
  6. Send video(s) — reply to original (with fallback to plain send)
  7. Caption: ✓ Delivered — <mention>

Pinterest URL support:
  - pin.it short URLs (expanded via HEAD request)
  - pinterest.com/pin/
  - pinterest.com/video/
  - Carousel pins (multiple media items)
  - Private pins (graceful error)

No progress messages for Pinterest.
"""
import asyncio
import re
import tempfile
from pathlib import Path
from typing import Optional, List

import aiohttp
from yt_dlp import YoutubeDL
from aiogram.types import Message, FSInputFile

from core.bot import bot
from core.config import config
from workers.task_queue import download_semaphore
from utils.logger import logger
from utils.cache import url_cache
from utils.media_processor import (
    ensure_fits_telegram, instagram_smart_encode,
    get_video_info,
)
from ui.formatting import format_delivered_with_mention
from ui.stickers import send_sticker, delete_sticker

# ─── URL validation ───────────────────────────────────────────────────────────

_PINTEREST_URL_RE = re.compile(
    r"https?://(www\.)?(pinterest\.(com|co\.\w+|fr|de|es|it|pt|ru|jp|kr|nz|au|ca|mx|cl|ar|br|in|ph|id|vn|th|tr|se|no|dk|fi|nl|be|at|ch|pl|cz|hu|ro|bg|hr|sk|si|lt|lv|ee|gr|cy|mt|lu|ie|is|li|mc|sm|va|ad|ba|rs|me|mk|al|xk|ge|am|az|by|md|ua|kz|kg|tj|tm|uz|mn|af|pk|bd|lk|np|bt|mv|mm|kh|la|vn|bn|tl|pg|fj|sb|vu|ws|to|ki|nr|pw|fm|mh|ck|nu|tk|wf|pf|nc|gu|mp|as|vi|pr|um|mq|gp|re|yt|pm|bl|mf|gf|sr|gy|aw|cw|sx|bq|ai|vg|ky|tc|ms|ag|dm|lc|vc|bb|tt|gd|kn|jm|ht|do|cu|bs|bz|gt|hn|sv|ni|cr|pa|co|ve|ec|pe|bo|py|uy|cl|ar|br)|pin\.it)/",
    re.IGNORECASE,
)

def _is_valid_pinterest_url(url: str) -> bool:
    """Validate that URL is a Pinterest URL"""
    url_lower = url.lower()
    return "pinterest." in url_lower or "pin.it/" in url_lower

def _sanitize_filename(name: str) -> str:
    """Remove unsafe characters from filename"""
    # Remove characters that are unsafe for filenames
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    # Collapse multiple underscores/spaces
    safe = re.sub(r'[_\s]+', '_', safe).strip('_')
    return safe[:100] or "pinterest_video"

# ─── URL resolver ─────────────────────────────────────────────────────────────

async def _resolve_pin_url(url: str) -> str:
    """
    Resolve pin.it shortened URL to full Pinterest URL.
    Uses aiohttp HEAD request (non-blocking). Falls back to original on error.
    """
    if "pin.it/" not in url:
        return url
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(
                url,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": config.pick_user_agent()},
            ) as resp:
                resolved = str(resp.url)
                logger.debug(f"Pinterest resolved: {url} → {resolved}")
                return resolved
    except Exception as e:
        logger.debug(f"Pinterest URL resolve failed (HEAD): {e}")
        # Fallback: try GET redirect
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    allow_redirects=True,
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers={"User-Agent": config.pick_user_agent()},
                ) as resp:
                    return str(resp.url)
        except Exception as e2:
            logger.debug(f"Pinterest URL resolve failed (GET): {e2}")
            return url

# ─── Download ─────────────────────────────────────────────────────────────────

async def _download_pinterest(url: str, tmp: Path) -> List[Path]:
    """
    Download Pinterest video(s) with yt-dlp.
    Supports single videos and carousel pins (multiple media).
    Returns list of downloaded file paths.
    """
    safe_title = _sanitize_filename("pin_%(id)s")
    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(tmp / f"{safe_title}.%(ext)s"),
        "proxy": config.pick_proxy(),
        "http_headers": {"User-Agent": config.pick_user_agent()},
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "ignoreerrors": True,  # Don't crash on private/unavailable items in carousel
    }

    # Primary: merge best video + audio to mp4
    opts_primary = {
        **base_opts,
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }],
    }

    try:
        with YoutubeDL(opts_primary) as ydl:
            await asyncio.to_thread(lambda: ydl.download([url]))
        files = (
            list(tmp.glob("*.mp4")) + list(tmp.glob("*.webm")) +
            list(tmp.glob("*.mkv")) + list(tmp.glob("*.mov"))
        )
        if files:
            return sorted(files)
    except Exception as e:
        logger.debug(f"Pinterest primary download failed: {type(e).__name__}: {str(e)[:100]}")

    # Fallback: best single format, no merge
    opts_fallback = {
        **base_opts,
        "format": "best[ext=mp4]/best",
        "ignoreerrors": True,
    }

    try:
        with YoutubeDL(opts_fallback) as ydl:
            await asyncio.to_thread(lambda: ydl.download([url]))
        files = (
            list(tmp.glob("*.mp4")) + list(tmp.glob("*.webm")) +
            list(tmp.glob("*.mkv")) + list(tmp.glob("*.mov"))
        )
        if files:
            return sorted(files)
    except Exception as e:
        logger.debug(f"Pinterest fallback download failed: {type(e).__name__}: {str(e)[:100]}")

    return []

# ─── Safe reply helpers ───────────────────────────────────────────────────────

async def _safe_reply_video(m: Message, **kwargs) -> Optional[Message]:
    """
    Try to reply to original message. If message not found, send normally.
    """
    try:
        return await bot.send_video(
            m.chat.id,
            reply_to_message_id=m.message_id,
            **kwargs,
        )
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "bad request" in err_str:
            try:
                return await bot.send_video(m.chat.id, **kwargs)
            except Exception as e2:
                logger.error(f"PIN send_video fallback failed: {e2}")
                return None
        logger.error(f"PIN send_video failed: {e}")
        return None

async def _safe_reply_text(m: Message, text: str, **kwargs) -> Optional[Message]:
    """
    Try to reply to original message. If message not found, send normally.
    """
    try:
        return await m.reply(text, **kwargs)
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "bad request" in err_str:
            try:
                return await bot.send_message(m.chat.id, text, **kwargs)
            except Exception as e2:
                logger.error(f"PIN send_message fallback failed: {e2}")
                return None
        logger.error(f"PIN reply failed: {e}")
        return None

# ─── Main handler ─────────────────────────────────────────────────────────────

async def handle_pinterest(m: Message, url: str):
    """
    Download Pinterest video pins (single + carousel).
    Cache-first → download → encode → send.
    Silent processing — no progress messages.
    Reply to original message with ✓ Delivered — <mention>.
    """
    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    delivered_caption = format_delivered_with_mention(user_id, first_name)

    sticker_msg_id = None

    # Validate URL
    if not _is_valid_pinterest_url(url):
        await _safe_reply_text(
            m,
            "⚠ Unable to process this link.\n\nPlease try again.",
            parse_mode="HTML",
        )
        return

    # Resolve shortened URL first
    if "pin.it/" in url:
        url = await _resolve_pin_url(url)
        logger.info(f"PINTEREST: Resolved to {url}")

    # Cache check (single video only)
    cached = await url_cache.get(url, "video")
    if cached:
        try:
            sent = await _safe_reply_video(
                m,
                video=cached,
                caption=delivered_caption,
                parse_mode="HTML",
                supports_streaming=True,
            )
            if sent:
                return
        except Exception:
            pass  # Stale cache — fall through

    async with download_semaphore:
        logger.info(f"PINTEREST: {url}")

        # Send sticker — no progress text message
        sticker_msg_id = await send_sticker(bot, m.chat.id, "pinterest")

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)

                video_files = await _download_pinterest(url, tmp)

                if not video_files:
                    await delete_sticker(bot, m.chat.id, sticker_msg_id)
                    sticker_msg_id = None
                    await _safe_reply_text(
                        m,
                        "⚠ Unable to process this link.\n\nPlease try again.",
                        parse_mode="HTML",
                    )
                    return

                # Delete sticker before sending
                await delete_sticker(bot, m.chat.id, sticker_msg_id)
                sticker_msg_id = None

                total_sent = 0
                for video_idx, video_file in enumerate(video_files):
                    if not video_file.exists():
                        logger.warning(f"PIN: File {video_file} does not exist, skipping")
                        continue

                    # Smart encode: stream copy if compatible, else adaptive
                    encoded = tmp / f"pin_enc_{video_idx}.mp4"
                    ok = await instagram_smart_encode(video_file, encoded)
                    final = encoded if ok and encoded.exists() else video_file

                    # File size check
                    file_size_mb = final.stat().st_size / (1024 * 1024)
                    logger.debug(f"PIN: File size {file_size_mb:.1f}MB")

                    parts = await ensure_fits_telegram(final, tmp)

                    for i, part in enumerate(parts):
                        if not part.exists():
                            logger.warning(f"PIN: Part {i} does not exist, skipping")
                            continue
                        info = await get_video_info(part)
                        # Caption on last part of last video
                        is_last = (video_idx == len(video_files) - 1) and (i == len(parts) - 1)
                        cap = delivered_caption if is_last else f"Part {i+1}/{len(parts)}" if len(parts) > 1 else ""
                        sent = await _safe_reply_video(
                            m,
                            video=FSInputFile(part),
                            caption=cap,
                            parse_mode="HTML",
                            supports_streaming=True,
                            width=info.get("width") or None,
                            height=info.get("height") or None,
                            duration=int(info.get("duration") or 0) or None,
                        )
                        total_sent += 1
                        # Cache single-video, single-part result
                        if sent and sent.video and len(video_files) == 1 and len(parts) == 1:
                            await url_cache.set(url, "video", sent.video.file_id)

                logger.info(f"PINTEREST: Sent {total_sent} file(s) to {user_id}")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"PINTEREST ERROR: {e}", exc_info=True)
            await delete_sticker(bot, m.chat.id, sticker_msg_id)
            sticker_msg_id = None
            await _safe_reply_text(
                m,
                "⚠ Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
        finally:
            if sticker_msg_id:
                await delete_sticker(bot, m.chat.id, sticker_msg_id)
