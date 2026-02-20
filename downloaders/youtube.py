"""
YouTube Downloader — Silent delivery with sticker support.

Flow (normal video):
  1. Send sticker
  2. Show inline [🎥 Video] [🎧 Audio] buttons (minimal status)
  3. Both streams download in background simultaneously
  4. User taps → send when ready
  5. Delete sticker + status message after send
  6. Reply to original with ✓ Delivered — <mention>

Shorts:
  Send sticker → silent download → delete sticker → send → ✓ Delivered — <mention>

YT Music:
  Send sticker → silent download → delete sticker → send → ✓ Delivered — <mention>

Cache:
  SHA256(url+format) → Telegram file_id
  If cached → send instantly, no re-download

Cookie folder:
  Never crash if folder missing — skip silently

Resolution rule:
  <= 120s → keep original (max 1080p)
  >  120s → 720p
"""
import asyncio
import time
import tempfile
from pathlib import Path
from typing import Optional

from yt_dlp import YoutubeDL
from aiogram.types import (
    Message, FSInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
)

from core.bot import bot, dp
from core.config import config
from workers.task_queue import download_semaphore
from utils.helpers import get_random_cookie
from utils.logger import logger
from utils.cache import url_cache
from utils.media_processor import (
    reencode_shorts, ensure_fits_telegram,
    get_video_info,
)
from utils.watchdog import acquire_user_slot, release_user_slot
from ui.formatting import format_delivered_with_mention
from ui.stickers import send_sticker, delete_sticker

# ─── URL detection ────────────────────────────────────────────────────────────

def is_youtube_short(url: str) -> bool:
    return "/shorts/" in url.lower()

def is_youtube_music(url: str) -> bool:
    return "music.youtube.com" in url.lower()

# ─── yt-dlp option builders ───────────────────────────────────────────────────

def _base_opts(tmp: Path) -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(tmp / "%(title)s.%(ext)s"),
        "proxy": config.pick_proxy(),
        "http_headers": {"User-Agent": config.pick_user_agent()},
        "socket_timeout": 30,
        "retries": 2,
        "fragment_retries": 2,
        "ignoreerrors": False,
    }

def _layer1_opts(tmp: Path, fmt: str) -> dict:
    opts = _base_opts(tmp)
    opts["format"] = fmt
    return opts

def _layer2_opts(tmp: Path, fmt: str) -> dict:
    opts = _base_opts(tmp)
    opts["format"] = fmt
    opts["extractor_args"] = {"youtube": {"player_client": ["android", "web"]}}
    opts["http_headers"]["User-Agent"] = (
        "com.google.android.youtube/17.36.4 (Linux; U; Android 12) gzip"
    )
    return opts

def _layer3_opts(tmp: Path, fmt: str) -> dict:
    opts = _base_opts(tmp)
    opts["format"] = fmt
    cookie_file = get_random_cookie(config.YT_COOKIES_FOLDER)
    if cookie_file:
        opts["cookiefile"] = cookie_file
    return opts

def _layer3_music_opts(tmp: Path, fmt: str) -> dict:
    opts = _base_opts(tmp)
    opts["format"] = fmt
    cookie_file = get_random_cookie(config.YT_MUSIC_COOKIES_FOLDER)
    if cookie_file:
        opts["cookiefile"] = cookie_file
    return opts

# ─── Download helpers ─────────────────────────────────────────────────────────

async def _try_download(url: str, opts: dict) -> Optional[Path]:
    """Attempt yt-dlp download. Returns file path or None."""
    tmp = Path(opts["outtmpl"]).parent
    try:
        with YoutubeDL(opts) as ydl:
            await asyncio.to_thread(lambda: ydl.download([url]))
        files = (
            list(tmp.glob("*.mp4")) + list(tmp.glob("*.webm")) +
            list(tmp.glob("*.mkv")) + list(tmp.glob("*.m4v"))
        )
        return files[0] if files else None
    except Exception as e:
        logger.debug(f"yt-dlp layer failed: {type(e).__name__}: {str(e)[:100]}")
        return None

async def download_youtube_video(
    url: str,
    tmp: Path,
    fmt: str = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
) -> Optional[Path]:
    """Download YouTube video — 3-layer fallback"""
    for layer_fn in [_layer1_opts, _layer2_opts, _layer3_opts]:
        opts = layer_fn(tmp, fmt)
        result = await _try_download(url, opts)
        if result:
            return result
    return None

async def download_youtube_audio(url: str, tmp: Path, is_music: bool = False) -> Optional[Path]:
    """Download YouTube/YT Music audio as 320kbps MP3"""
    fmt = "bestaudio[ext=m4a]/bestaudio/best"
    layer_fns = [_layer1_opts, _layer2_opts]
    layer_fns.append(_layer3_music_opts if is_music else _layer3_opts)

    for layer_fn in layer_fns:
        opts = layer_fn(tmp, fmt)
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        }]
        opts["outtmpl"] = str(tmp / "%(title)s.%(ext)s")
        try:
            with YoutubeDL(opts) as ydl:
                await asyncio.to_thread(lambda: ydl.download([url]))
            mp3_files = list(tmp.glob("*.mp3"))
            if mp3_files:
                return mp3_files[0]
        except Exception as e:
            logger.debug(f"Audio layer failed: {str(e)[:80]}")

    return None

# ─── Safe reply helpers ───────────────────────────────────────────────────────

async def _safe_send_video(chat_id: int, reply_to_msg_id: Optional[int], **kwargs) -> Optional[Message]:
    """
    Try to send video with reply. If message not found, send without reply.
    """
    try:
        return await bot.send_video(
            chat_id,
            reply_to_message_id=reply_to_msg_id,
            **kwargs,
        )
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "bad request" in err_str:
            try:
                return await bot.send_video(chat_id, **kwargs)
            except Exception as e2:
                logger.error(f"YT send_video fallback failed: {e2}")
                return None
        logger.error(f"YT send_video failed: {e}")
        return None

async def _safe_send_audio(chat_id: int, reply_to_msg_id: Optional[int], **kwargs) -> Optional[Message]:
    """
    Try to send audio with reply. If message not found, send without reply.
    """
    try:
        return await bot.send_audio(
            chat_id,
            reply_to_message_id=reply_to_msg_id,
            **kwargs,
        )
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "bad request" in err_str:
            try:
                return await bot.send_audio(chat_id, **kwargs)
            except Exception as e2:
                logger.error(f"YT send_audio fallback failed: {e2}")
                return None
        logger.error(f"YT send_audio failed: {e}")
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
                logger.error(f"YT send_message fallback failed: {e2}")
                return None
        logger.error(f"YT reply failed: {e}")
        return None

# ─── Pending job store (for inline button flow) ───────────────────────────────
_pending: dict = {}

# ─── YT Music handler ────────────────────────────────────────────────────────

async def handle_youtube_music(m: Message, url: str):
    """
    YT Music → 320kbps MP3.
    Silent: sticker → download → delete sticker → send → ✓ Delivered — <mention>
    """
    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    delivered_caption = format_delivered_with_mention(user_id, first_name)

    # Cache check
    cached = await url_cache.get(url, "audio")
    if cached:
        try:
            sent = await _safe_send_audio(
                m.chat.id,
                m.message_id,
                audio=cached,
                caption=delivered_caption,
                parse_mode="HTML",
            )
            if sent:
                return
        except Exception:
            pass

    # Send sticker — no progress text message
    sticker_msg_id = await send_sticker(bot, m.chat.id, "music")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            audio_file = await download_youtube_audio(url, tmp, is_music=True)

            if not audio_file or not audio_file.exists():
                await delete_sticker(bot, m.chat.id, sticker_msg_id)
                await _safe_reply_text(
                    m,
                    "⚠ Unable to process this link.\n\nPlease try again.",
                    parse_mode="HTML",
                )
                return

            await delete_sticker(bot, m.chat.id, sticker_msg_id)
            sticker_msg_id = None

            sent = await _safe_send_audio(
                m.chat.id,
                m.message_id,
                audio=FSInputFile(audio_file),
                caption=delivered_caption,
                parse_mode="HTML",
            )

            if sent and sent.audio:
                await url_cache.set(url, "audio", sent.audio.file_id)

            logger.info(f"YT MUSIC: Sent to {user_id}")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"YT MUSIC ERROR: {e}", exc_info=True)
        await delete_sticker(bot, m.chat.id, sticker_msg_id)
        await _safe_reply_text(
            m,
            "⚠ Unable to process this link.\n\nPlease try again.",
            parse_mode="HTML",
        )

# ─── Shorts handler ───────────────────────────────────────────────────────────

async def handle_youtube_short(m: Message, url: str):
    """
    YouTube Shorts — Silent: sticker → download → delete sticker → send → ✓ Delivered — <mention>
    No progress messages.
    """
    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    delivered_caption = format_delivered_with_mention(user_id, first_name)

    # Cache check
    cached = await url_cache.get(url, "video")
    if cached:
        try:
            sent = await _safe_send_video(
                m.chat.id,
                m.message_id,
                video=cached,
                caption=delivered_caption,
                parse_mode="HTML",
                supports_streaming=True,
            )
            if sent:
                return
        except Exception:
            pass

    # Send sticker — no progress text message
    sticker_msg_id = await send_sticker(bot, m.chat.id, "youtube")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            video_file = await download_youtube_video(
                url, tmp,
                fmt="bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            )

            if not video_file or not video_file.exists():
                await delete_sticker(bot, m.chat.id, sticker_msg_id)
                await _safe_reply_text(
                    m,
                    "⚠ Unable to process this link.\n\nPlease try again.",
                    parse_mode="HTML",
                )
                return

            encoded = tmp / "short_enc.mp4"
            ok = await reencode_shorts(video_file, encoded)
            final = encoded if ok and encoded.exists() else video_file

            info = await get_video_info(final)
            parts = await ensure_fits_telegram(final, tmp)

            await delete_sticker(bot, m.chat.id, sticker_msg_id)
            sticker_msg_id = None

            for i, part in enumerate(parts):
                if not part.exists():
                    logger.warning(f"YT SHORT: Part {i} does not exist, skipping")
                    continue
                pi = await get_video_info(part)
                cap = delivered_caption if i == len(parts) - 1 else f"Part {i+1}/{len(parts)}"
                sent = await _safe_send_video(
                    m.chat.id,
                    m.message_id,
                    video=FSInputFile(part),
                    caption=cap,
                    parse_mode="HTML",
                    supports_streaming=True,
                    width=pi.get("width") or info.get("width") or None,
                    height=pi.get("height") or info.get("height") or None,
                    duration=int(pi.get("duration") or info.get("duration") or 0) or None,
                )
                if sent and sent.video and len(parts) == 1:
                    await url_cache.set(url, "video", sent.video.file_id)

            logger.info(f"SHORTS: Sent to {user_id}")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"SHORTS ERROR: {e}", exc_info=True)
        await delete_sticker(bot, m.chat.id, sticker_msg_id)
        await _safe_reply_text(
            m,
            "⚠ Unable to process this link.\n\nPlease try again.",
            parse_mode="HTML",
        )

# ─── Normal video handler ─────────────────────────────────────────────────────

async def handle_youtube_normal(m: Message, url: str):
    """
    Normal YouTube video:
    1. Send sticker
    2. Show inline [🎥 Video] [🎧 Audio] buttons (minimal status — no progress bar)
    3. Both streams download in background simultaneously
    4. User taps → send when ready
    5. Delete sticker + status message after send
    6. Caption: ✓ Delivered — <mention>
    """
    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    job_key = f"yt:{user_id}:{int(time.time())}"

    # Send sticker first
    sticker_msg_id = await send_sticker(bot, m.chat.id, "youtube")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎥 Video", callback_data=f"yt_video:{job_key}"),
        InlineKeyboardButton(text="🎧 Audio", callback_data=f"yt_audio:{job_key}"),
    ]])

    # Minimal status — just the format picker, no progress bar
    try:
        status = await m.reply(
            "Choose format:",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "bad request" in err_str:
            try:
                status = await bot.send_message(
                    m.chat.id,
                    "Choose format:",
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            except Exception as e2:
                logger.error(f"YT NORMAL: Could not send format picker: {e2}")
                await delete_sticker(bot, m.chat.id, sticker_msg_id)
                return
        else:
            logger.error(f"YT NORMAL: Could not send format picker: {e}")
            await delete_sticker(bot, m.chat.id, sticker_msg_id)
            return

    tmp_dir_obj = tempfile.TemporaryDirectory()
    tmp = Path(tmp_dir_obj.name)

    loop = asyncio.get_running_loop()
    video_future: asyncio.Future = loop.create_future()
    audio_future: asyncio.Future = loop.create_future()

    _pending[job_key] = {
        "video_future": video_future,
        "audio_future": audio_future,
        "tmp_dir": tmp_dir_obj,
        "tmp": tmp,
        "url": url,
        "chat_id": m.chat.id,
        "user_id": user_id,
        "first_name": first_name,
        "status_id": status.message_id,
        "sticker_msg_id": sticker_msg_id,
        "original_msg_id": m.message_id,
        "created_at": time.time(),
    }

    asyncio.create_task(_bg_download_video(job_key, url, tmp, video_future))
    asyncio.create_task(_bg_download_audio(job_key, url, tmp, audio_future))
    asyncio.create_task(_cleanup_pending(job_key, delay=600))

async def _bg_download_video(job_key: str, url: str, tmp: Path, future: asyncio.Future):
    """Background video download"""
    try:
        async with download_semaphore:
            video_file = await download_youtube_video(url, tmp)
            if not future.done():
                future.set_result(video_file)
    except Exception as e:
        logger.error(f"BG video error: {e}")
        if not future.done():
            future.set_result(None)

async def _bg_download_audio(job_key: str, url: str, tmp: Path, future: asyncio.Future):
    """Background audio download"""
    try:
        async with download_semaphore:
            audio_file = await download_youtube_audio(url, tmp)
            if not future.done():
                future.set_result(audio_file)
    except Exception as e:
        logger.error(f"BG audio error: {e}")
        if not future.done():
            future.set_result(None)

async def _cleanup_pending(job_key: str, delay: int = 600):
    """Clean up pending job after timeout"""
    await asyncio.sleep(delay)
    job = _pending.pop(job_key, None)
    if job:
        try:
            job["tmp_dir"].cleanup()
        except Exception:
            pass

# ─── Callback handlers ────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data and c.data.startswith("yt_video:"))
async def cb_yt_video(callback: CallbackQuery):
    """Video button tap"""
    job_key = callback.data.split(":", 1)[1]
    job = _pending.get(job_key)

    if not job:
        await callback.answer("Session expired. Send the link again.", show_alert=True)
        return

    await callback.answer("⏳ Preparing video...")

    chat_id = job["chat_id"]
    url = job["url"]
    user_id = job["user_id"]
    first_name = job.get("first_name", "User")
    original_msg_id = job.get("original_msg_id")
    sticker_msg_id = job.get("sticker_msg_id")
    delivered_caption = format_delivered_with_mention(user_id, first_name)

    # Delete status message and sticker immediately
    try:
        await bot.delete_message(chat_id, job["status_id"])
    except Exception:
        pass
    await delete_sticker(bot, chat_id, sticker_msg_id)

    # Cache check
    cached = await url_cache.get(url, "video")
    if cached:
        try:
            sent = await _safe_send_video(
                chat_id,
                original_msg_id,
                video=cached,
                caption=delivered_caption,
                parse_mode="HTML",
                supports_streaming=True,
            )
            if sent:
                return
        except Exception:
            pass

    try:
        try:
            video_file = await asyncio.wait_for(
                asyncio.shield(job["video_future"]),
                timeout=config.DOWNLOAD_TIMEOUT,
            )
        except asyncio.TimeoutError:
            await bot.send_message(
                chat_id,
                "⚠ Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
            return

        if not video_file or not video_file.exists():
            await bot.send_message(
                chat_id,
                "⚠ Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
            return

        tmp = job["tmp"]
        parts = await ensure_fits_telegram(video_file, tmp)

        for i, part in enumerate(parts):
            if not part.exists():
                logger.warning(f"YT VIDEO: Part {i} does not exist, skipping")
                continue
            info = await get_video_info(part)
            cap = delivered_caption if i == len(parts) - 1 else f"Part {i+1}/{len(parts)}"
            sent = await _safe_send_video(
                chat_id,
                original_msg_id,
                video=FSInputFile(part),
                caption=cap,
                parse_mode="HTML",
                supports_streaming=True,
                width=info.get("width") or None,
                height=info.get("height") or None,
                duration=int(info.get("duration") or 0) or None,
            )
            if sent and sent.video and len(parts) == 1:
                await url_cache.set(url, "video", sent.video.file_id)

        logger.info(f"YT VIDEO: Sent {len(parts)} part(s) to {user_id}")

    except Exception as e:
        logger.error(f"YT VIDEO CALLBACK ERROR: {e}", exc_info=True)
        try:
            await bot.send_message(
                chat_id,
                "⚠ Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
        except Exception:
            pass


@dp.callback_query(lambda c: c.data and c.data.startswith("yt_audio:"))
async def cb_yt_audio(callback: CallbackQuery):
    """Audio button tap"""
    job_key = callback.data.split(":", 1)[1]
    job = _pending.get(job_key)

    if not job:
        await callback.answer("Session expired. Send the link again.", show_alert=True)
        return

    await callback.answer("⏳ Preparing audio...")

    chat_id = job["chat_id"]
    url = job["url"]
    user_id = job["user_id"]
    first_name = job.get("first_name", "User")
    original_msg_id = job.get("original_msg_id")
    sticker_msg_id = job.get("sticker_msg_id")
    delivered_caption = format_delivered_with_mention(user_id, first_name)

    # Delete status message and sticker immediately
    try:
        await bot.delete_message(chat_id, job["status_id"])
    except Exception:
        pass
    await delete_sticker(bot, chat_id, sticker_msg_id)

    # Cache check
    cached = await url_cache.get(url, "audio")
    if cached:
        try:
            sent = await _safe_send_audio(
                chat_id,
                original_msg_id,
                audio=cached,
                caption=delivered_caption,
                parse_mode="HTML",
            )
            if sent:
                return
        except Exception:
            pass

    try:
        try:
            audio_file = await asyncio.wait_for(
                asyncio.shield(job["audio_future"]),
                timeout=config.DOWNLOAD_TIMEOUT,
            )
        except asyncio.TimeoutError:
            await bot.send_message(
                chat_id,
                "⚠ Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
            return

        if not audio_file or not audio_file.exists():
            await bot.send_message(
                chat_id,
                "⚠ Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
            return

        sent = await _safe_send_audio(
            chat_id,
            original_msg_id,
            audio=FSInputFile(audio_file),
            caption=delivered_caption,
            parse_mode="HTML",
        )

        if sent and sent.audio:
            await url_cache.set(url, "audio", sent.audio.file_id)

        logger.info(f"YT AUDIO: Sent to {user_id}")

    except Exception as e:
        logger.error(f"YT AUDIO CALLBACK ERROR: {e}", exc_info=True)
        try:
            await bot.send_message(
                chat_id,
                "⚠ Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
        except Exception:
            pass

# ─── Main entry point ─────────────────────────────────────────────────────────

async def handle_youtube(m: Message, url: str):
    """Route YouTube URL to appropriate handler"""
    if not await acquire_user_slot(m.from_user.id, config.MAX_CONCURRENT_PER_USER):
        try:
            await m.reply("⏳ You have downloads in progress. Please wait.", parse_mode="HTML")
        except Exception:
            await bot.send_message(
                m.chat.id,
                "⏳ You have downloads in progress. Please wait.",
                parse_mode="HTML",
            )
        return

    try:
        if is_youtube_music(url):
            async with download_semaphore:
                await handle_youtube_music(m, url)
        elif is_youtube_short(url):
            async with download_semaphore:
                await handle_youtube_short(m, url)
        else:
            await handle_youtube_normal(m, url)
    finally:
        await release_user_slot(m.from_user.id)
