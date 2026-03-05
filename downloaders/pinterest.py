"""
Pinterest Downloader — Ultra-fast delivery with photo + video + carousel support.

Flow:
  1. Resolve pin.it short URLs
  2. Cache check → instant if cached
  3. Send sticker
  4. Download (single-stream, no merge, no re-encode)
  5. Delete sticker → send media → ✓ Delivered — "mention"

Supports:
  - Video pins (sent as video)
  - Photo pins (sent as photo)
  - Carousel pins (multiple media)
  - pin.it short URLs

Speed optimized:
  - Single-stream format (no merge)
  - No re-encoding (stream copy only)
  - 15s timeout, 2 retries
"""
import asyncio
import re
import tempfile
import time
from pathlib import Path
from typing import Optional, List

import aiohttp
from yt_dlp import YoutubeDL
from aiogram.types import Message, FSInputFile

from core.bot import bot
from core.config import config
from workers.task_queue import download_semaphore
from utils.logger import logger
from utils.proxy_manager import proxy_manager
from utils.cache import url_cache
from utils.media_processor import ensure_fits_telegram, get_video_info
from utils.watchdog import acquire_user_slot, release_user_slot
from ui.formatting import safe_caption, build_safe_media_caption
from ui.stickers import send_sticker, delete_sticker
from ui.emoji_config import get_emoji_async
from utils.log_channel import log_download

# ─── URL helpers ──────────────────────────────────────────────────────────────

def _is_valid_pinterest_url(url: str) -> bool:
    url_lower = url.lower()
    return "pinterest." in url_lower or "pin.it/" in url_lower

def _sanitize_filename(name: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    safe = re.sub(r'[_\s]+', '_', safe).strip('_')
    return safe[:100] or "pin"

async def _resolve_pin_url(url: str) -> str:
    """Resolve pin.it → full Pinterest URL via HEAD redirect."""
    if "pin.it/" not in url:
        return url
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(
                url, allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=8),
                headers={"User-Agent": config.pick_user_agent()},
            ) as resp:
                return str(resp.url)
    except Exception:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, allow_redirects=True,
                    timeout=aiohttp.ClientTimeout(total=8),
                    headers={"User-Agent": config.pick_user_agent()},
                ) as resp:
                    return str(resp.url)
        except Exception:
            return url

# ─── Download (fast, single-stream) ──────────────────────────────────────────

def _is_image(path: Path) -> bool:
    """Check if file is an image by extension."""
    return path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif")

def _is_video(path: Path) -> bool:
    """Check if file is a video by extension."""
    return path.suffix.lower() in (".mp4", ".webm", ".mkv", ".mov", ".m4v")

async def _download_pinterest(url: str, tmp: Path) -> List[Path]:
    """
    Download Pinterest media — videos AND photos.
    Single-stream format for speed. No merge.
    """
    safe_title = _sanitize_filename("pin_%(id)s")
    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "outtmpl": str(tmp / f"{safe_title}.%(ext)s"),
        "proxy": proxy_manager.pick_proxy(),
        "http_headers": {"User-Agent": config.pick_user_agent()},
        "socket_timeout": 15,
        "retries": 2,
        "fragment_retries": 2,
        "ignoreerrors": True,
        "writethumbnail": False,
    }

    # Try single-stream first (fastest)
    opts = {**base_opts, "format": "best[ext=mp4]/best"}
    try:
        with YoutubeDL(opts) as ydl:
            await asyncio.to_thread(lambda: ydl.download([url]))
    except Exception as e:
        logger.debug(f"Pinterest download failed: {type(e).__name__}: {str(e)[:100]}")

    # Collect ALL downloaded files — videos and images
    files = sorted(
        list(tmp.glob("*.mp4")) + list(tmp.glob("*.webm")) +
        list(tmp.glob("*.mkv")) + list(tmp.glob("*.mov")) +
        list(tmp.glob("*.jpg")) + list(tmp.glob("*.jpeg")) +
        list(tmp.glob("*.png")) + list(tmp.glob("*.webp")) +
        list(tmp.glob("*.gif"))
    )
    return files

# ─── Safe send helpers ────────────────────────────────────────────────────────

async def _safe_reply_video(m: Message, **kwargs) -> Optional[Message]:
    """Send video with reply fallback chain."""
    if "caption" in kwargs and kwargs["caption"]:
        kwargs["caption"] = safe_caption(kwargs["caption"])
    try:
        return await bot.send_video(m.chat.id, reply_to_message_id=m.message_id, **kwargs)
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "replied message not found" in err_str:
            try:
                return await bot.send_video(m.chat.id, **kwargs)
            except Exception as e2:
                if "entity_text_invalid" in str(e2).lower():
                    kwargs.pop("caption", None)
                    kwargs.pop("parse_mode", None)
                    try:
                        return await bot.send_video(m.chat.id, **kwargs)
                    except Exception:
                        return None
                return None
        if "entity_text_invalid" in err_str:
            kwargs.pop("caption", None)
            kwargs.pop("parse_mode", None)
            try:
                return await bot.send_video(m.chat.id, reply_to_message_id=m.message_id, **kwargs)
            except Exception:
                try:
                    return await bot.send_video(m.chat.id, **kwargs)
                except Exception:
                    return None
        logger.error(f"PIN send_video failed: {e}")
        return None

async def _safe_reply_photo(m: Message, **kwargs) -> Optional[Message]:
    """Send photo with reply fallback chain."""
    if "caption" in kwargs and kwargs["caption"]:
        kwargs["caption"] = safe_caption(kwargs["caption"])
    try:
        return await bot.send_photo(m.chat.id, reply_to_message_id=m.message_id, **kwargs)
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "replied message not found" in err_str:
            try:
                return await bot.send_photo(m.chat.id, **kwargs)
            except Exception:
                return None
        if "entity_text_invalid" in err_str:
            kwargs.pop("caption", None)
            kwargs.pop("parse_mode", None)
            try:
                return await bot.send_photo(m.chat.id, reply_to_message_id=m.message_id, **kwargs)
            except Exception:
                try:
                    return await bot.send_photo(m.chat.id, **kwargs)
                except Exception:
                    return None
        logger.error(f"PIN send_photo failed: {e}")
        return None

async def _safe_reply_text(m: Message, text: str, **kwargs) -> Optional[Message]:
    try:
        return await m.reply(text, **kwargs)
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "bad request" in err_str:
            try:
                return await bot.send_message(m.chat.id, text, **kwargs)
            except Exception:
                return None
        return None

# ─── Main handler ─────────────────────────────────────────────────────────────

async def handle_pinterest(m: Message, url: str):
    """
    Download Pinterest pins — videos, photos, carousels.
    Ultra-fast: single-stream, no re-encode, cache-first.
    """
    if not await acquire_user_slot(m.from_user.id, config.MAX_CONCURRENT_PER_USER):
        _proc = await get_emoji_async("PROCESS")
        try:
            await m.reply(f"{_proc} You have downloads in progress. Please wait.", parse_mode="HTML")
        except Exception:
            pass
        return

    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    delivered_emoji = await get_emoji_async("DELIVERED")
    delivered_caption = build_safe_media_caption(user_id, first_name, delivered_emoji)
    _t_start = time.monotonic()

    sticker_msg_id = None

    try:
        if not _is_valid_pinterest_url(url):
            _err = await get_emoji_async("ERROR")
            await _safe_reply_text(m, f"{_err} Unable to process this link.\n\nPlease try again.", parse_mode="HTML")
            return

        # Resolve pin.it shortened URL
        if "pin.it/" in url:
            url = await _resolve_pin_url(url)

        # Cache check
        cached = await url_cache.get(url, "video")
        if cached:
            try:
                sent = await _safe_reply_video(m, video=cached, caption=delivered_caption, parse_mode="HTML", supports_streaming=True)
                if sent:
                    return
            except Exception:
                pass

        # Also check photo cache
        cached_photo = await url_cache.get(url, "photo")
        if cached_photo:
            try:
                sent = await _safe_reply_photo(m, photo=cached_photo, caption=delivered_caption, parse_mode="HTML")
                if sent:
                    return
            except Exception:
                pass

        async with download_semaphore:
            logger.info(f"PINTEREST: {url}")
            sticker_msg_id = await send_sticker(bot, m.chat.id, "pinterest")

            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp = Path(tmp_dir)
                    files = await _download_pinterest(url, tmp)

                    if not files:
                        await delete_sticker(bot, m.chat.id, sticker_msg_id)
                        sticker_msg_id = None
                        _err = await get_emoji_async("ERROR")
                        await _safe_reply_text(m, f"{_err} Unable to process this link.\n\nPlease try again.", parse_mode="HTML")
                        return

                    await delete_sticker(bot, m.chat.id, sticker_msg_id)
                    sticker_msg_id = None

                    total_sent = 0
                    for idx, file_path in enumerate(files):
                        if not file_path.exists():
                            continue

                        is_last = (idx == len(files) - 1)
                        cap = delivered_caption if is_last else ""

                        if _is_image(file_path):
                            # Send as photo
                            sent = await _safe_reply_photo(m, photo=FSInputFile(file_path), caption=cap, parse_mode="HTML")
                            if sent and sent.photo and len(files) == 1:
                                await url_cache.set(url, "photo", sent.photo[-1].file_id)
                            total_sent += 1

                        elif _is_video(file_path):
                            # Ensure video fits Telegram (no re-encode, just size check)
                            parts = await ensure_fits_telegram(file_path, tmp)
                            for i, part in enumerate(parts):
                                if not part.exists():
                                    continue
                                info = await get_video_info(part)
                                part_is_last = is_last and (i == len(parts) - 1)
                                part_cap = delivered_caption if part_is_last else ""
                                sent = await _safe_reply_video(
                                    m, video=FSInputFile(part), caption=part_cap, parse_mode="HTML",
                                    supports_streaming=True,
                                    width=info.get("width") or None,
                                    height=info.get("height") or None,
                                    duration=int(info.get("duration") or 0) or None,
                                )
                                total_sent += 1
                                if sent and sent.video and len(files) == 1 and len(parts) == 1:
                                    await url_cache.set(url, "video", sent.video.file_id)

                    logger.info(f"PINTEREST: Sent {total_sent} file(s) to {user_id}")
                    _elapsed = time.monotonic() - _t_start
                    asyncio.create_task(log_download(user=m.from_user, link=url, chat=m.chat, media_type="Media (Pinterest)", time_taken=_elapsed))

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"PINTEREST ERROR: {e}", exc_info=True)
                await delete_sticker(bot, m.chat.id, sticker_msg_id)
                sticker_msg_id = None
                _err = await get_emoji_async("ERROR")
                await _safe_reply_text(m, f"{_err} Unable to process this link.\n\nPlease try again.", parse_mode="HTML")
            finally:
                if sticker_msg_id:
                    await delete_sticker(bot, m.chat.id, sticker_msg_id)

    finally:
        await release_user_slot(m.from_user.id)
