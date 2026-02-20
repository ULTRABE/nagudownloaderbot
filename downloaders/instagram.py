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
import glob
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
from utils.cache import url_cache
from utils.media_processor import (
    ensure_fits_telegram, instagram_smart_encode,
    get_video_info,
)
from utils.watchdog import acquire_user_slot, release_user_slot
from ui.formatting import format_delivered_with_mention
from ui.stickers import send_sticker, delete_sticker
from utils.log_channel import log_download

# ─── Layered extraction ───────────────────────────────────────────────────────

def _base_opts(tmp: Path) -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(tmp / "%(title)s.%(ext)s"),
        "proxy": config.pick_proxy(),
        "http_headers": {"User-Agent": config.pick_user_agent()},
        "socket_timeout": 30,
        "retries": 2,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    }

def _layer1_opts(tmp: Path) -> dict:
    return _base_opts(tmp)

def _layer2_opts(tmp: Path) -> dict:
    opts = _base_opts(tmp)
    opts["http_headers"]["User-Agent"] = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram/303.0"
    )
    return opts

def _layer3_opts(tmp: Path) -> dict:
    """Cookie-based fallback — skip silently if no cookies"""
    opts = _base_opts(tmp)
    ig_cookies = (
        glob.glob("cookies_instagram*.txt") +
        [f for f in glob.glob("*.txt") if "instagram" in f.lower()]
    )
    if ig_cookies:
        opts["cookiefile"] = ig_cookies[0]
    return opts

async def _try_download(url: str, opts: dict) -> Optional[Path]:
    tmp = Path(opts["outtmpl"]).parent
    try:
        with YoutubeDL(opts) as ydl:
            await asyncio.to_thread(lambda: ydl.download([url]))
        files = (
            list(tmp.glob("*.mp4")) + list(tmp.glob("*.webm")) +
            list(tmp.glob("*.mov")) + list(tmp.glob("*.mkv"))
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
    Try to reply to original message. If message not found, send normally.
    Wraps every reply in try/except to prevent crashes.
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
                logger.error(f"IG send_video fallback failed: {e2}")
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
        await _safe_reply_text(m, "⏳ You have downloads in progress. Please wait.", parse_mode="HTML")
        return

    import time as _time_mod
    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    delivered_caption = format_delivered_with_mention(user_id, first_name)
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
                        await _safe_reply_text(
                            m,
                            "⚠ Unable to process this link.\n\nPlease try again.",
                            parse_mode="HTML",
                        )
                        return

                    # Smart encode
                    encoded = tmp / "ig_enc.mp4"
                    ok = await instagram_smart_encode(video_file, encoded)
                    final = encoded if ok and encoded.exists() else video_file

                    # File size check
                    file_size_mb = final.stat().st_size / (1024 * 1024)
                    if file_size_mb > config.TG_VIDEO_LIMIT_MB * 2:
                        logger.warning(f"IG: File too large ({file_size_mb:.1f}MB), splitting")

                    parts = await ensure_fits_telegram(final, tmp)

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
                    _chat_type = "Group" if m.chat.type in ("group", "supergroup") else "Private"
                    asyncio.create_task(log_download(
                        user=m.from_user,
                        link=url,
                        chat_type=_chat_type,
                        media_type="Video (Instagram)",
                        time_taken=_elapsed,
                    ))

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"INSTAGRAM ERROR: {e}", exc_info=True)
                await delete_sticker(bot, m.chat.id, sticker_msg_id)
                sticker_msg_id = None
                await _safe_reply_text(
                    m,
                    "⚠ Unable to process this link.\n\nPlease try again.",
                    parse_mode="HTML",
                )

    finally:
        await release_user_slot(m.from_user.id)
        if sticker_msg_id:
            await delete_sticker(bot, m.chat.id, sticker_msg_id)
