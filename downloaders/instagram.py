"""
Instagram Downloader — Silent delivery with cache + smart encode.

Flow:
  1. Send sticker (if enabled)
  2. Download silently (no progress messages)
  3. Delete sticker after delivery
  4. Send video — reply to original (with fallback to plain send)
  5. Caption: ✓ Delivered — <mention>

No progress messages for Instagram.
"""
import asyncio
import tempfile
from pathlib import Path
from typing import Optional

from yt_dlp import YoutubeDL
from aiogram.types import Message, FSInputFile

from core.bot import bot
from core.config import config
from workers.task_queue import download_semaphore
from utils.helpers import get_random_cookie
from utils.logger import logger
from utils.proxy_manager import proxy_manager
from utils.cache import url_cache
from utils.media_processor import (
    ensure_fits_telegram,
    get_video_info,
)
from utils.watchdog import acquire_user_slot, release_user_slot
from ui.formatting import format_delivered_with_mention, safe_caption, build_safe_media_caption
from ui.stickers import send_sticker, delete_sticker
from ui.emoji_config import get_emoji_async
from utils.log_channel import log_download

# ─── Layered extraction ───────────────────────────────────────────────────────

def _base_opts(tmp: Path) -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "outtmpl": str(tmp / "%(title)s.%(ext)s"),
        "proxy": proxy_manager.pick_proxy(),
        "http_headers": {"User-Agent": config.pick_user_agent()},
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "format": "best[ext=mp4]/best",
    }

def _layer1_opts(tmp: Path) -> dict:
    return _base_opts(tmp)

def _layer2_opts(tmp: Path) -> dict:
    opts = _base_opts(tmp)
    opts["http_headers"]["User-Agent"] = (
        "Instagram 344.0.0.0.0 Android (33/13; 420dpi; 1080x2400; "
        "samsung; SM-S918B; dm3q; qcom; en_US; 605596538)"
    )
    return opts

def _layer3_opts(tmp: Path) -> dict:
    """Cookie-based fallback — skip silently if no cookies.
    Uses absolute path from config so it works regardless of CWD (Railway).
    """
    opts = _base_opts(tmp)
    # config.IG_COOKIES is an absolute path resolved from the project root
    ig_cookie = config.IG_COOKIES
    if ig_cookie and Path(ig_cookie).exists():
        opts["cookiefile"] = ig_cookie
    return opts

async def _try_download(url: str, opts: dict) -> Optional[Path]:
    tmp = Path(opts["outtmpl"]).parent
    try:
        with YoutubeDL(opts) as ydl:
            await asyncio.to_thread(lambda: ydl.download([url]))
        # Video files first, then images (for photo posts)
        files = (
            list(tmp.glob("*.mp4")) + list(tmp.glob("*.webm")) +
            list(tmp.glob("*.mov")) + list(tmp.glob("*.mkv")) +
            list(tmp.glob("*.jpg")) + list(tmp.glob("*.jpeg")) +
            list(tmp.glob("*.png")) + list(tmp.glob("*.webp"))
        )
        return files[0] if files else None
    except Exception as e:
        logger.debug(f"IG layer failed: {type(e).__name__}: {str(e)[:80]}")
        return None

async def download_instagram(url: str, tmp: Path) -> Optional[Path]:
    """3-layer Instagram download"""
    for layer_fn in [_layer1_opts, _layer2_opts, _layer3_opts]:
        opts = layer_fn(tmp)
        result = await _try_download(url, opts)
        if result:
            return result
    return None

# ─── Safe reply helper ────────────────────────────────────────────────────────

async def _safe_reply_video(m: Message, **kwargs) -> Optional[Message]:
    """
    Try to reply to original message.
    Fallback chain:
      1. With reply_to_message_id
      2. Without reply (if reply target not found)
      3. Without caption (if ENTITY_TEXT_INVALID — bad HTML in caption)
    """
    # Sanitize caption before sending
    if "caption" in kwargs and kwargs["caption"]:
        kwargs["caption"] = safe_caption(kwargs["caption"])

    try:
        return await bot.send_video(
            m.chat.id,
            reply_to_message_id=m.message_id,
            **kwargs,
        )
    except Exception as e:
        err_str = str(e).lower()

        # Reply target gone — retry without reply
        if "message to be replied not found" in err_str or "replied message not found" in err_str:
            try:
                return await bot.send_video(m.chat.id, **kwargs)
            except Exception as e2:
                err_str2 = str(e2).lower()
                if "entity_text_invalid" in err_str2 or "bad request" in err_str2:
                    logger.warning(f"IG send_video: caption invalid, retrying without caption")
                    kwargs.pop("caption", None)
                    kwargs.pop("parse_mode", None)
                    try:
                        return await bot.send_video(m.chat.id, **kwargs)
                    except Exception as e3:
                        logger.error(f"IG send_video no-caption fallback failed: {e3}")
                        return None
                logger.error(f"IG send_video fallback failed: {e2}")
                return None

        # Caption entity error — strip caption and retry
        if "entity_text_invalid" in err_str or "bad request" in err_str:
            logger.warning(f"IG send_video: ENTITY_TEXT_INVALID, retrying without caption. Error: {e}")
            kwargs.pop("caption", None)
            kwargs.pop("parse_mode", None)
            try:
                return await bot.send_video(
                    m.chat.id,
                    reply_to_message_id=m.message_id,
                    **kwargs,
                )
            except Exception as e2:
                try:
                    return await bot.send_video(m.chat.id, **kwargs)
                except Exception as e3:
                    logger.error(f"IG send_video no-caption fallback failed: {e3}")
                    return None

        logger.error(f"IG send_video failed: {e}")
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
                logger.error(f"IG send_message fallback failed: {e2}")
                return None
        logger.error(f"IG reply failed: {e}")
        return None

# ─── Main handler ─────────────────────────────────────────────────────────────

async def handle_instagram(m: Message, url: str):
    """
    Download Instagram posts, reels, stories.
    Cache-first → stream copy → adaptive encode.
    Silent processing — no progress messages.
    Reply to original message with ✓ Delivered — <mention>.
    """
    if not await acquire_user_slot(m.from_user.id, config.MAX_CONCURRENT_PER_USER):
        _proc = await get_emoji_async("PROCESS")
        await _safe_reply_text(m, f"{_proc} You have downloads in progress. Please wait.", parse_mode="HTML")
        return

    import time as _time_mod
    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    # Build sanitized caption via centralized builder — prevents ENTITY_TEXT_INVALID
    from ui.emoji_config import get_emoji_async as _get_emoji
    delivered_emoji = await _get_emoji("DELIVERED")
    delivered_caption = build_safe_media_caption(user_id, first_name, delivered_emoji)
    _t_start = _time_mod.monotonic()

    sticker_msg_id = None

    try:
        # Cache check
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
            logger.info(f"INSTAGRAM: {url}")

            # Send sticker — no progress text message
            sticker_msg_id = await send_sticker(bot, m.chat.id, "instagram")

            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp = Path(tmp_dir)

                    video_file = await download_instagram(url, tmp)

                    if not video_file or not video_file.exists():
                        await delete_sticker(bot, m.chat.id, sticker_msg_id)
                        sticker_msg_id = None
                        _err = await get_emoji_async("ERROR")
                        await _safe_reply_text(
                            m,
                            f"{_err} Unable to process this link.\n\nPlease try again.",
                            parse_mode="HTML",
                        )
                        return

                    # Skip re-encoding — just ensure fits Telegram
                    parts = await ensure_fits_telegram(video_file, tmp)

                    # Delete sticker before sending
                    await delete_sticker(bot, m.chat.id, sticker_msg_id)
                    sticker_msg_id = None

                    for i, part in enumerate(parts):
                        if not part.exists():
                            logger.warning(f"IG: Part {i} does not exist, skipping")
                            continue
                        info = await get_video_info(part)
                        cap = delivered_caption if i == len(parts) - 1 else f"Part {i+1}/{len(parts)}"
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
                        # Cache single-part result
                        if sent and sent.video and len(parts) == 1:
                            await url_cache.set(url, "video", sent.video.file_id)

                    logger.info(f"INSTAGRAM: Sent {len(parts)} file(s) to {user_id}")

                    # Log to channel
                    _elapsed = _time_mod.monotonic() - _t_start
                    asyncio.create_task(log_download(
                        user=m.from_user,
                        link=url,
                        chat=m.chat,
                        media_type="Video (Instagram)",
                        time_taken=_elapsed,
                    ))

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"INSTAGRAM ERROR: {e}", exc_info=True)
                await delete_sticker(bot, m.chat.id, sticker_msg_id)
                sticker_msg_id = None
                _err = await get_emoji_async("ERROR")
                await _safe_reply_text(
                    m,
                    f"{_err} Unable to process this link.\n\nPlease try again.",
                    parse_mode="HTML",
                )

    finally:
        await release_user_slot(m.from_user.id)
        if sticker_msg_id:
            await delete_sticker(bot, m.chat.id, sticker_msg_id)
