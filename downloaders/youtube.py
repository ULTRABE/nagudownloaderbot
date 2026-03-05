"""
YouTube Downloader — Silent delivery with sticker support.

Flow (normal video):
  1. Send sticker
  2. Show inline [🎥 Video] [🎧 Audio] colored buttons (user-locked)
  3. Both streams download in background simultaneously
  4. User taps → send when ready
  5. Delete sticker + status message after send
  6. Reply to original with ✓ Delivered — <mention>

Shorts:
  Send sticker → silent download → delete sticker → send → ✓ Delivered

YT Music:
  Send sticker → silent download → delete sticker → send → ✓ Delivered

Extraction layers (4-layer fallback):
  1. Default client (no special config)
  2. mweb + ios clients (avoids 403 on desktop-blocked content)
  3. Cookies (authenticated access)
  4. Cookies + mweb (ultimate fallback)

Cache:
  SHA256(url+format) → Telegram file_id → instant re-delivery

Cookie folder:
  Never crash if folder missing — skip silently

>50MB fix:
  CRF-based adaptive encode → constrained bitrate fallback
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
from utils.proxy_manager import proxy_manager
from utils.cache import url_cache
from utils.media_processor import (
    get_video_info, get_file_size, _run_ffmpeg,
)
from utils.watchdog import acquire_user_slot, release_user_slot
from ui.formatting import safe_caption, build_safe_media_caption
from ui.stickers import send_sticker, delete_sticker
from ui.emoji_config import get_emoji_async
from utils.log_channel import log_download

# ─── URL detection ────────────────────────────────────────────────────────────

def is_youtube_short(url: str) -> bool:
    return "/shorts/" in url.lower()

def is_youtube_music(url: str) -> bool:
    """YT Music single track — NOT a playlist"""
    url_lower = url.lower()
    if "music.youtube.com" not in url_lower:
        return False
    if "playlist" in url_lower or ("list=" in url_lower and "watch" not in url_lower):
        return False
    return True

# ─── yt-dlp option builders (4-layer fallback) ───────────────────────────────

def _base_opts(tmp: Path) -> dict:
    """Base yt-dlp options — optimized for speed"""
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
        "extractor_retries": 2,
        "ignoreerrors": False,
    }

def _layer1_opts(tmp: Path, fmt: str) -> dict:
    """Layer 1: Default client — works for most content"""
    opts = _base_opts(tmp)
    opts["format"] = fmt
    return opts

def _layer2_opts(tmp: Path, fmt: str) -> dict:
    """Layer 2: mweb + ios clients — avoids 403 on desktop-blocked content"""
    opts = _base_opts(tmp)
    opts["format"] = fmt
    opts["extractor_args"] = {"youtube": {"player_client": ["mweb", "ios"]}}
    return opts

def _layer3_opts(tmp: Path, fmt: str) -> dict:
    """Layer 3: Cookies — authenticated access"""
    opts = _base_opts(tmp)
    opts["format"] = fmt
    cookie_file = get_random_cookie(config.YT_COOKIES_FOLDER)
    if cookie_file:
        opts["cookiefile"] = cookie_file
    return opts

def _layer4_opts(tmp: Path, fmt: str) -> dict:
    """Layer 4: Cookies + mweb — ultimate fallback"""
    opts = _base_opts(tmp)
    opts["format"] = fmt
    opts["extractor_args"] = {"youtube": {"player_client": ["mweb"]}}
    cookie_file = get_random_cookie(config.YT_COOKIES_FOLDER)
    if cookie_file:
        opts["cookiefile"] = cookie_file
    return opts

def _layer3_music_opts(tmp: Path, fmt: str) -> dict:
    """Layer 3 (Music): YT Music cookies"""
    opts = _base_opts(tmp)
    opts["format"] = fmt
    cookie_file = get_random_cookie(config.YT_MUSIC_COOKIES_FOLDER)
    if cookie_file:
        opts["cookiefile"] = cookie_file
    return opts

def _layer4_music_opts(tmp: Path, fmt: str) -> dict:
    """Layer 4 (Music): YT Music cookies + mweb"""
    opts = _base_opts(tmp)
    opts["format"] = fmt
    opts["extractor_args"] = {"youtube": {"player_client": ["mweb"]}}
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
    fmt: str = "best[height<=720][ext=mp4]/best[height<=720]/bestvideo[height<=720]+bestaudio/best",
) -> Optional[Path]:
    """Download YouTube video — 4-layer fallback for maximum reliability"""
    for layer_fn in [_layer1_opts, _layer2_opts, _layer3_opts, _layer4_opts]:
        opts = layer_fn(tmp, fmt)
        result = await _try_download(url, opts)
        if result:
            return result
    return None

async def download_youtube_audio(url: str, tmp: Path, is_music: bool = False, quality: str = "192") -> Optional[Path]:
    """Download YouTube/YT Music audio as MP3 — 4-layer fallback"""
    fmt = "bestaudio[ext=m4a]/bestaudio/best"
    layer_fns = [_layer1_opts, _layer2_opts]
    if is_music:
        layer_fns.extend([_layer3_music_opts, _layer4_music_opts])
    else:
        layer_fns.extend([_layer3_opts, _layer4_opts])

    for layer_fn in layer_fns:
        opts = layer_fn(tmp, fmt)
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": quality,
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

# ─── Ensure video fits Telegram (>50MB fix) ───────────────────────────────────

async def ensure_video_fits_telegram(video_path: Path, tmp_dir: Path) -> Optional[Path]:
    """
    Ensure video fits Telegram 49MB limit.
    Uses CRF-based adaptive encode from media_processor.
    """
    from utils.media_processor import adaptive_encode

    TG_LIMIT = 49 * 1024 * 1024
    size = get_file_size(video_path)

    if size <= TG_LIMIT:
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
                return remuxed
        return video_path

    logger.info(f"YT VIDEO: {size/1024/1024:.1f}MB exceeds 49MB, CRF encode")

    encoded = tmp_dir / f"enc_{video_path.stem}.mp4"
    ok = await adaptive_encode(video_path, encoded)

    if ok and encoded.exists() and get_file_size(encoded) <= TG_LIMIT:
        logger.info(f"YT VIDEO: Encoded to {get_file_size(encoded)/1024/1024:.1f}MB")
        return encoded

    # Fallback: 720p CRF encode
    fallback = tmp_dir / f"fallback_{video_path.stem}.mp4"
    ok2 = await adaptive_encode(video_path, fallback, force_height=720, force_crf=28)
    if ok2 and fallback.exists():
        logger.info(f"YT VIDEO: 720p fallback {get_file_size(fallback)/1024/1024:.1f}MB")
        return fallback

    return video_path

# ─── Safe reply helpers ───────────────────────────────────────────────────────

async def _safe_send_video(chat_id: int, reply_to_msg_id: Optional[int], **kwargs) -> Optional[Message]:
    """Send video with reply fallback chain."""
    if "caption" in kwargs and kwargs["caption"]:
        kwargs["caption"] = safe_caption(kwargs["caption"])
    try:
        return await bot.send_video(chat_id, reply_to_message_id=reply_to_msg_id, **kwargs)
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "replied message not found" in err_str:
            try:
                return await bot.send_video(chat_id, **kwargs)
            except Exception as e2:
                if "entity_text_invalid" in str(e2).lower() or "bad request" in str(e2).lower():
                    kwargs.pop("caption", None)
                    kwargs.pop("parse_mode", None)
                    try:
                        return await bot.send_video(chat_id, **kwargs)
                    except Exception:
                        return None
                return None
        if "entity_text_invalid" in err_str or "bad request" in err_str:
            kwargs.pop("caption", None)
            kwargs.pop("parse_mode", None)
            try:
                return await bot.send_video(chat_id, reply_to_message_id=reply_to_msg_id, **kwargs)
            except Exception:
                try:
                    return await bot.send_video(chat_id, **kwargs)
                except Exception:
                    return None
        logger.error(f"YT send_video failed: {e}")
        return None

async def _safe_send_audio(chat_id: int, reply_to_msg_id: Optional[int], **kwargs) -> Optional[Message]:
    """Send audio with reply fallback chain."""
    if "caption" in kwargs and kwargs["caption"]:
        kwargs["caption"] = safe_caption(kwargs["caption"])
    try:
        return await bot.send_audio(chat_id, reply_to_message_id=reply_to_msg_id, **kwargs)
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "replied message not found" in err_str:
            try:
                return await bot.send_audio(chat_id, **kwargs)
            except Exception as e2:
                if "entity_text_invalid" in str(e2).lower() or "bad request" in str(e2).lower():
                    kwargs.pop("caption", None)
                    kwargs.pop("parse_mode", None)
                    try:
                        return await bot.send_audio(chat_id, **kwargs)
                    except Exception:
                        return None
                return None
        if "entity_text_invalid" in err_str or "bad request" in err_str:
            kwargs.pop("caption", None)
            kwargs.pop("parse_mode", None)
            try:
                return await bot.send_audio(chat_id, reply_to_message_id=reply_to_msg_id, **kwargs)
            except Exception:
                try:
                    return await bot.send_audio(chat_id, **kwargs)
                except Exception:
                    return None
        logger.error(f"YT send_audio failed: {e}")
        return None

async def _safe_reply_text(m: Message, text: str, **kwargs) -> Optional[Message]:
    """Reply with fallback to plain send."""
    try:
        return await m.reply(text, **kwargs)
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "replied message not found" in err_str:
            try:
                return await bot.send_message(m.chat.id, text, **kwargs)
            except Exception:
                return None
        logger.error(f"YT reply failed: {e}")
        return None

# ─── Pending job store (for inline button flow) ───────────────────────────────
_pending: dict = {}

# ─── YT Music handler ────────────────────────────────────────────────────────

async def handle_youtube_music(m: Message, url: str):
    """YT Music → 320kbps MP3. Silent delivery."""
    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    delivered_emoji = await get_emoji_async("DELIVERED")
    delivered_caption = build_safe_media_caption(user_id, first_name, delivered_emoji)
    _t_start = time.monotonic()

    # Cache check
    cached = await url_cache.get(url, "audio")
    if cached:
        try:
            sent = await _safe_send_audio(m.chat.id, m.message_id, audio=cached, caption=delivered_caption, parse_mode="HTML")
            if sent:
                return
        except Exception:
            pass

    sticker_msg_id = await send_sticker(bot, m.chat.id, "music")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            audio_file = await download_youtube_audio(url, tmp, is_music=True)

            if not audio_file or not audio_file.exists():
                await delete_sticker(bot, m.chat.id, sticker_msg_id)
                _err = await get_emoji_async("ERROR")
                await _safe_reply_text(m, f"{_err} Unable to process this link.\n\nPlease try again.", parse_mode="HTML")
                return

            await delete_sticker(bot, m.chat.id, sticker_msg_id)
            sticker_msg_id = None

            sent = await _safe_send_audio(m.chat.id, m.message_id, audio=FSInputFile(audio_file), caption=delivered_caption, parse_mode="HTML")
            if sent and sent.audio:
                await url_cache.set(url, "audio", sent.audio.file_id)

            logger.info(f"YT MUSIC: Sent to {user_id}")
            _elapsed = time.monotonic() - _t_start
            asyncio.create_task(log_download(user=m.from_user, link=url, chat=m.chat, media_type="Audio (YT Music)", time_taken=_elapsed))

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"YT MUSIC ERROR: {e}", exc_info=True)
        await delete_sticker(bot, m.chat.id, sticker_msg_id)
        _err = await get_emoji_async("ERROR")
        await _safe_reply_text(m, f"{_err} Unable to process this link.\n\nPlease try again.", parse_mode="HTML")

# ─── Shorts handler ───────────────────────────────────────────────────────────

async def handle_youtube_short(m: Message, url: str):
    """YouTube Shorts — silent download, max quality."""
    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    delivered_emoji = await get_emoji_async("DELIVERED")
    delivered_caption = build_safe_media_caption(user_id, first_name, delivered_emoji)
    _t_start = time.monotonic()

    # Cache check
    cached = await url_cache.get(url, "video")
    if cached:
        try:
            sent = await _safe_send_video(m.chat.id, m.message_id, video=cached, caption=delivered_caption, parse_mode="HTML", supports_streaming=True)
            if sent:
                return
        except Exception:
            pass

    sticker_msg_id = await send_sticker(bot, m.chat.id, "youtube")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            # Single-stream format — no merge needed = instant download
            video_file = await download_youtube_video(url, tmp, fmt="best[height<=720][ext=mp4]/best[height<=720]/best")

            if not video_file or not video_file.exists():
                await delete_sticker(bot, m.chat.id, sticker_msg_id)
                _err = await get_emoji_async("ERROR")
                await _safe_reply_text(m, f"{_err} Unable to process this link.\n\nPlease try again.", parse_mode="HTML")
                return

            # Skip re-encoding — just ensure fits Telegram (stream copy if needed)
            final = await ensure_video_fits_telegram(video_file, tmp) or video_file
            info = await get_video_info(final)

            await delete_sticker(bot, m.chat.id, sticker_msg_id)
            sticker_msg_id = None

            sent = await _safe_send_video(
                m.chat.id, m.message_id,
                video=FSInputFile(final), caption=delivered_caption, parse_mode="HTML",
                supports_streaming=True,
                width=info.get("width") or None,
                height=info.get("height") or None,
                duration=int(info.get("duration") or 0) or None,
            )
            if sent and sent.video:
                await url_cache.set(url, "video", sent.video.file_id)

            logger.info(f"SHORTS: Sent to {user_id}")
            _elapsed = time.monotonic() - _t_start
            asyncio.create_task(log_download(user=m.from_user, link=url, chat=m.chat, media_type="Video (Short)", time_taken=_elapsed))

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"SHORTS ERROR: {e}", exc_info=True)
        await delete_sticker(bot, m.chat.id, sticker_msg_id)
        _err = await get_emoji_async("ERROR")
        await _safe_reply_text(m, f"{_err} Unable to process this link.\n\nPlease try again.", parse_mode="HTML")

# ─── Normal video handler (user-locked colored buttons) ───────────────────────

async def handle_youtube_normal(m: Message, url: str):
    """
    Normal YouTube video with user-locked colored format picker.
    Only the user who sent the link can tap the buttons.
    """
    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    job_key = f"yt:{user_id}:{int(time.time())}"

    sticker_msg_id = await send_sticker(bot, m.chat.id, "youtube")

    # User-locked buttons: encode user_id in callback_data
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎥 Video", callback_data=f"yt_video:{user_id}:{job_key}", style="primary"),
        InlineKeyboardButton(text="🎧 Audio", callback_data=f"yt_audio:{user_id}:{job_key}", style="success"),
    ]])

    _yt = await get_emoji_async("YT")
    try:
        status = await m.reply(f"{_yt} <b>𝐂𝐡𝐨𝐨𝐬𝐞 𝐅𝐨𝐫𝐦𝐚𝐭</b>", reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "bad request" in err_str:
            try:
                status = await bot.send_message(m.chat.id, f"{_yt} <b>𝐂𝐡𝐨𝐨𝐬𝐞 𝐅𝐨𝐫𝐦𝐚𝐭</b>", reply_markup=keyboard, parse_mode="HTML")
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
    asyncio.create_task(_cleanup_pending(job_key, delay=300))

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

async def _cleanup_pending(job_key: str, delay: int = 300):
    """Clean up pending job after timeout"""
    await asyncio.sleep(delay)
    job = _pending.pop(job_key, None)
    if job:
        try:
            job["tmp_dir"].cleanup()
        except Exception:
            pass

# ─── User-locked callback handlers ────────────────────────────────────────────

def _parse_user_locked_callback(data: str, prefix: str):
    """Parse user-locked callback data: prefix:user_id:job_key → (owner_id, job_key)"""
    rest = data[len(prefix):]
    parts = rest.split(":", 1)
    if len(parts) < 2:
        return None, None
    try:
        return int(parts[0]), parts[1]
    except (ValueError, TypeError):
        return None, None


@dp.callback_query(lambda c: c.data and c.data.startswith("yt_video:"))
async def cb_yt_video(callback: CallbackQuery):
    """Video button tap — user-locked"""
    owner_id, job_key = _parse_user_locked_callback(callback.data, "yt_video:")
    if owner_id and callback.from_user.id != owner_id:
        await callback.answer("⛔ This is not your download.", show_alert=True)
        return

    job = _pending.get(job_key)
    if not job:
        await callback.answer("Session expired. Send the link again.", show_alert=True)
        return

    await callback.answer("Preparing video...")

    chat_id = job["chat_id"]
    url = job["url"]
    user_id = job["user_id"]
    first_name = job.get("first_name", "User")
    original_msg_id = job.get("original_msg_id")
    sticker_msg_id = job.get("sticker_msg_id")
    delivered_emoji = await get_emoji_async("DELIVERED")
    delivered_caption = build_safe_media_caption(user_id, first_name, delivered_emoji)

    try:
        await bot.delete_message(chat_id, job["status_id"])
    except Exception:
        pass
    await delete_sticker(bot, chat_id, sticker_msg_id)

    # Cache check
    cached = await url_cache.get(url, "video")
    if cached:
        try:
            sent = await _safe_send_video(chat_id, original_msg_id, video=cached, caption=delivered_caption, parse_mode="HTML", supports_streaming=True)
            if sent:
                return
        except Exception:
            pass

    try:
        try:
            video_file = await asyncio.wait_for(asyncio.shield(job["video_future"]), timeout=config.DOWNLOAD_TIMEOUT)
        except asyncio.TimeoutError:
            _err = await get_emoji_async("ERROR")
            await bot.send_message(chat_id, f"{_err} Download timed out. Please try again.", parse_mode="HTML")
            return

        if not video_file or not video_file.exists():
            _err = await get_emoji_async("ERROR")
            await bot.send_message(chat_id, f"{_err} Unable to process this link.\n\nPlease try again.", parse_mode="HTML")
            return

        final_video = await ensure_video_fits_telegram(video_file, job["tmp"]) or video_file
        info = await get_video_info(final_video)

        sent = await _safe_send_video(
            chat_id, original_msg_id,
            video=FSInputFile(final_video), caption=delivered_caption, parse_mode="HTML",
            supports_streaming=True,
            width=info.get("width") or None, height=info.get("height") or None,
            duration=int(info.get("duration") or 0) or None,
        )
        if sent and sent.video:
            await url_cache.set(url, "video", sent.video.file_id)

        logger.info(f"YT VIDEO: Sent to {user_id}")
        asyncio.create_task(log_download(
            user=type("U", (), {"id": user_id, "first_name": first_name})(),
            link=url, chat_type="Private", media_type="Video", time_taken=0.0,
        ))

    except Exception as e:
        logger.error(f"YT VIDEO CALLBACK ERROR: {e}", exc_info=True)
        try:
            _err = await get_emoji_async("ERROR")
            await bot.send_message(chat_id, f"{_err} Unable to process this link.\n\nPlease try again.", parse_mode="HTML")
        except Exception:
            pass


@dp.callback_query(lambda c: c.data and c.data.startswith("yt_audio:"))
async def cb_yt_audio(callback: CallbackQuery):
    """Audio button tap — user-locked"""
    owner_id, job_key = _parse_user_locked_callback(callback.data, "yt_audio:")
    if owner_id and callback.from_user.id != owner_id:
        await callback.answer("⛔ This is not your download.", show_alert=True)
        return

    job = _pending.get(job_key)
    if not job:
        await callback.answer("Session expired. Send the link again.", show_alert=True)
        return

    await callback.answer("Preparing audio...")

    chat_id = job["chat_id"]
    url = job["url"]
    user_id = job["user_id"]
    first_name = job.get("first_name", "User")
    original_msg_id = job.get("original_msg_id")
    sticker_msg_id = job.get("sticker_msg_id")
    delivered_emoji = await get_emoji_async("DELIVERED")
    delivered_caption = build_safe_media_caption(user_id, first_name, delivered_emoji)

    try:
        await bot.delete_message(chat_id, job["status_id"])
    except Exception:
        pass
    await delete_sticker(bot, chat_id, sticker_msg_id)

    # Cache check
    cached = await url_cache.get(url, "audio")
    if cached:
        try:
            sent = await _safe_send_audio(chat_id, original_msg_id, audio=cached, caption=delivered_caption, parse_mode="HTML")
            if sent:
                return
        except Exception:
            pass

    try:
        try:
            audio_file = await asyncio.wait_for(asyncio.shield(job["audio_future"]), timeout=config.DOWNLOAD_TIMEOUT)
        except asyncio.TimeoutError:
            _err = await get_emoji_async("ERROR")
            await bot.send_message(chat_id, f"{_err} Download timed out. Please try again.", parse_mode="HTML")
            return

        if not audio_file or not audio_file.exists():
            _err = await get_emoji_async("ERROR")
            await bot.send_message(chat_id, f"{_err} Unable to process this link.\n\nPlease try again.", parse_mode="HTML")
            return

        sent = await _safe_send_audio(chat_id, original_msg_id, audio=FSInputFile(audio_file), caption=delivered_caption, parse_mode="HTML")
        if sent and sent.audio:
            await url_cache.set(url, "audio", sent.audio.file_id)

        logger.info(f"YT AUDIO: Sent to {user_id}")
        asyncio.create_task(log_download(
            user=type("U", (), {"id": user_id, "first_name": first_name})(),
            link=url, chat_type="Private", media_type="Audio", time_taken=0.0,
        ))

    except Exception as e:
        logger.error(f"YT AUDIO CALLBACK ERROR: {e}", exc_info=True)
        try:
            _err = await get_emoji_async("ERROR")
            await bot.send_message(chat_id, f"{_err} Unable to process this link.\n\nPlease try again.", parse_mode="HTML")
        except Exception:
            pass

# ─── Main entry point ─────────────────────────────────────────────────────────

async def handle_youtube(m: Message, url: str):
    """Route YouTube URL to appropriate handler (no playlist support)"""
    if not await acquire_user_slot(m.from_user.id, config.MAX_CONCURRENT_PER_USER):
        _proc = await get_emoji_async("PROCESS")
        try:
            await m.reply(f"{_proc} You have downloads in progress. Please wait.", parse_mode="HTML")
        except Exception:
            await bot.send_message(m.chat.id, f"{_proc} You have downloads in progress. Please wait.", parse_mode="HTML")
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
