"""
Instagram Downloader — Silent delivery with cache + smart encode.

Flow:
  1. Send sticker (if enabled)
  2. Download silently (no progress messages)
     - Layer 1: direct (no proxy)
     - Layer 2: proxy + Instagram mobile UA (parallel with Layer 1)
     - Layer 3: cookies from ig_cookies folder (sequential, up to 50 accounts)
     - Layer 4: cookies + proxy (last resort)
  3. Delete sticker after delivery
  4. Send video — reply to original (with fallback to plain send)
  5. Caption: ✓ Delivered — <mention>

Cookie support:
  - Place up to 50 Netscape cookie files in "ig cookies/" folder
  - Falls back to single cookies_instagram.txt if folder not present
  - Works WITHOUT cookies too — cookies only used as fallback

Age-restricted / N18+ content:
  - Bypassed automatically when cookies are available
  - age_limit set to 100 on all layers
"""
import asyncio
import random
import tempfile
import time
from pathlib import Path
from typing import Optional, List

from yt_dlp import YoutubeDL
from aiogram.types import Message, FSInputFile

from core.bot import bot
from core.config import config
from workers.task_queue import download_semaphore
from utils.logger import logger
from utils.proxy_manager import proxy_manager
from utils.cache import url_cache
from utils.media_processor import (
    ensure_fits_telegram,
    get_video_info,
)
from utils.watchdog import acquire_user_slot, release_user_slot
from ui.formatting import safe_caption, build_safe_media_caption
from ui.stickers import send_sticker, delete_sticker
from ui.emoji_config import get_emoji_async
from utils.log_channel import log_download

# ─── Cookie helpers ────────────────────────────────────────────────────────────

def _get_ig_cookie() -> Optional[str]:
    """
    Get a random Instagram cookie file.
    Priority: ig cookies/ folder (up to 50 files) → cookies_instagram.txt fallback.
    Returns path string or None.
    """
    # Try multi-cookie folder first
    ig_folder = config.IG_COOKIES_FOLDER
    folder_path = Path(ig_folder)
    if folder_path.exists() and folder_path.is_dir():
        cookies = list(folder_path.glob("*.txt"))
        if cookies:
            return str(random.choice(cookies))

    # Fallback to single cookie file
    single = config.IG_COOKIES
    if single and Path(single).exists():
        return single

    return None

def _get_all_ig_cookies() -> List[str]:
    """
    Get all available Instagram cookie file paths.
    Used for rotating through all accounts on repeated failures.
    """
    cookies = []
    # Multi-cookie folder
    ig_folder = config.IG_COOKIES_FOLDER
    folder_path = Path(ig_folder)
    if folder_path.exists() and folder_path.is_dir():
        cookies.extend([str(p) for p in sorted(folder_path.glob("*.txt"))])

    # Single file (deduplicate)
    single = config.IG_COOKIES
    if single and Path(single).exists() and single not in cookies:
        cookies.append(single)

    return cookies

# ─── Layered extraction ───────────────────────────────────────────────────────

def _base_opts(tmp: Path, use_proxy: bool = False) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "outtmpl": str(tmp / "%(title)s.%(ext)s"),
        "http_headers": {"User-Agent": config.pick_user_agent()},
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "ignoreerrors": False,
        "format": "best[ext=mp4]/best",
        # Age-restricted content bypass
        "age_limit": 100,
    }
    if use_proxy:
        proxy = proxy_manager.pick_proxy()
        if proxy:
            opts["proxy"] = proxy
    return opts


async def _try_download(url: str, opts: dict) -> Optional[Path]:
    tmp = Path(opts["outtmpl"]).parent
    try:
        with YoutubeDL(opts) as ydl:
            await asyncio.to_thread(lambda: ydl.download([url]))
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
    """
    Instagram download — parallel fast layers + cookie fallback.
    Layer 1 (direct) + Layer 2 (proxy+IG UA) run in PARALLEL.
    Layer 3+ (cookies, up to 50 accounts) as sequential fallback.
    Age-restricted/N18+ content bypassed via cookies automatically.
    """
    # Fast parallel: direct + proxy with Instagram mobile UA
    l1 = _base_opts(tmp, use_proxy=False)

    l2 = _base_opts(tmp, use_proxy=True)
    l2["http_headers"] = {
        "User-Agent": (
            "Instagram 344.0.0.0.0 Android (33/13; 420dpi; 1080x2400; "
            "samsung; SM-S918B; dm3q; qcom; en_US; 605596538)"
        )
    }

    # Run Layer 1 and Layer 2 in parallel
    results: dict = {}

    async def _attempt(idx: int, opts: dict):
        sub = tmp / f"ig_layer_{idx}"
        sub.mkdir(exist_ok=True)
        opts["outtmpl"] = str(sub / "%(title)s.%(ext)s")
        result = await _try_download(url, opts)
        if result:
            results[idx] = result

    await asyncio.gather(
        asyncio.create_task(_attempt(0, l1)),
        asyncio.create_task(_attempt(1, l2)),
        return_exceptions=True,
    )
    for i in sorted(results.keys()):
        return results[i]

    # Sequential cookie fallback: try each available IG account
    # This is the key path for age-restricted / private content
    all_cookies = _get_all_ig_cookies()

    if all_cookies:
        # Try a random cookie first for speed
        random.shuffle(all_cookies)
        for cookie_idx, cookie_file in enumerate(all_cookies[:10]):  # Max 10 attempts
            for use_proxy in [False, True]:
                sub_key = f"ig_cookie_{cookie_idx}_{int(use_proxy)}"
                sub = tmp / sub_key
                sub.mkdir(exist_ok=True)
                opts = _base_opts(tmp, use_proxy=use_proxy)
                opts["outtmpl"] = str(sub / "%(title)s.%(ext)s")
                opts["cookiefile"] = cookie_file
                # Extra Instagram-specific options for age-restricted content
                opts["extractor_args"] = {
                    "instagram": {
                        "app_id": "936619743392459",  # Instagram app ID
                    }
                }
                result = await _try_download(url, opts)
                if result:
                    logger.info(f"IG: Success with cookie #{cookie_idx + 1} proxy={use_proxy}")
                    return result
    else:
        # No cookies at all — try one more time with proxy only
        opts = _base_opts(tmp, use_proxy=True)
        sub = tmp / "ig_proxy_final"
        sub.mkdir(exist_ok=True)
        opts["outtmpl"] = str(sub / "%(title)s.%(ext)s")
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
                    logger.warning("IG send_video: caption invalid, retrying without caption")
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
    Download Instagram posts, reels, stories — including age-restricted content.
    Cache-first → stream copy → adaptive encode.
    Silent processing — no progress messages.
    Reply to original message with ✓ Delivered — <mention>.
    Supports multiple cookie accounts (up to 50) for maximum coverage.
    """
    if not await acquire_user_slot(m.from_user.id, config.MAX_CONCURRENT_PER_USER):
        _proc = await get_emoji_async("PROCESS")
        await _safe_reply_text(m, f"{_proc} You have downloads in progress. Please wait.", parse_mode="HTML")
        return

    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    delivered_emoji = await get_emoji_async("DELIVERED")
    delivered_caption = build_safe_media_caption(user_id, first_name, delivered_emoji)
    _t_start = time.monotonic()

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

                    # Ensure video fits Telegram (stream copy or CRF encode if needed)
                    parts = await ensure_fits_telegram(video_file, tmp)

                    # Delete sticker before sending
                    await delete_sticker(bot, m.chat.id, sticker_msg_id)
                    sticker_msg_id = None

                    sent_count = 0
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
                        sent_count += 1
                        # Cache single-part result
                        if sent and sent.video and len(parts) == 1:
                            await url_cache.set(url, "video", sent.video.file_id)

                    if sent_count == 0:
                        _err = await get_emoji_async("ERROR")
                        await _safe_reply_text(
                            m,
                            f"{_err} Unable to send this media.\n\nPlease try again.",
                            parse_mode="HTML",
                        )
                        return

                    logger.info(f"INSTAGRAM: Sent {len(parts)} file(s) to {user_id}")

                    # Log to channel
                    _elapsed = time.monotonic() - _t_start
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
                if sticker_msg_id:
                    await delete_sticker(bot, m.chat.id, sticker_msg_id)
                    sticker_msg_id = None
                _err = await get_emoji_async("ERROR")
                await _safe_reply_text(
                    m,
                    f"{_err} Unable to process this link.\n\nPlease try again.",
                    parse_mode="HTML",
                )

    finally:
        if sticker_msg_id:
            await delete_sticker(bot, m.chat.id, sticker_msg_id)
        await release_user_slot(m.from_user.id)
