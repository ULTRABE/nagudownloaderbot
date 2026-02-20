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

Playlist:
  Detect → show mode selector (Audio/Video)
  → show quality selector
  → download each item → send to DM
  → progress bar in original chat

Cache:
  SHA256(url+format) → Telegram file_id
  If cached → send instantly, no re-download

Cookie folder:
  Never crash if folder missing — skip silently

Resolution rule:
  <= 120s → keep original (max 1080p)
  >  120s → 720p

>50MB fix:
  Dynamic bitrate re-encode to fit under 49MB.
"""
import asyncio
import re
import time
import tempfile
from pathlib import Path
from typing import Optional

from yt_dlp import YoutubeDL
from aiogram.types import (
    Message, FSInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
)
from aiogram.exceptions import TelegramForbiddenError

from core.bot import bot, dp
from core.config import config
from workers.task_queue import download_semaphore
from utils.helpers import get_random_cookie
from utils.logger import logger
from utils.cache import url_cache
from utils.media_processor import (
    reencode_shorts,
    get_video_info, get_file_size, _run_ffmpeg,
)
from utils.watchdog import acquire_user_slot, release_user_slot
from ui.formatting import (
    format_delivered_with_mention,
    format_yt_playlist_mode,
    format_yt_audio_quality,
    format_yt_video_quality,
    format_yt_playlist_final,
)
from ui.stickers import send_sticker, delete_sticker
from ui.emoji_config import get_emoji_async
from utils.user_state import user_state_manager
from utils.log_channel import log_download

# ─── URL detection ────────────────────────────────────────────────────────────

def is_youtube_short(url: str) -> bool:
    return "/shorts/" in url.lower()

def is_youtube_music(url: str) -> bool:
    """YT Music single track — NOT a playlist"""
    url_lower = url.lower()
    if "music.youtube.com" not in url_lower:
        return False
    # If it's a playlist URL, don't treat as music
    if "playlist" in url_lower or ("list=" in url_lower and "watch" not in url_lower):
        return False
    return True

def is_youtube_playlist(url: str) -> bool:
    """Detect YouTube playlist URLs (including YT Music playlists)"""
    url_lower = url.lower()
    # youtube.com/playlist?list= or music.youtube.com/playlist?list=
    if "playlist" in url_lower and "list=" in url_lower:
        return True
    # youtube.com/watch?v=...&list= (only if list= is present and it's a real playlist)
    if ("youtube.com/watch" in url_lower or "youtu.be/" in url_lower) and "list=" in url_lower:
        # Exclude auto-generated "related" playlists (RD prefix)
        list_match = re.search(r"list=([^&]+)", url_lower)
        if list_match:
            list_id = list_match.group(1)
            # Only treat as playlist if it's a real playlist (not RD/auto-generated)
            if not list_id.startswith("rd") and not list_id.startswith("fl"):
                return True
    # music.youtube.com/watch?v=...&list= — treat as playlist
    if "music.youtube.com/watch" in url_lower and "list=" in url_lower:
        list_match = re.search(r"list=([^&]+)", url_lower)
        if list_match:
            list_id = list_match.group(1)
            if not list_id.startswith("rd") and not list_id.startswith("fl"):
                return True
    return False

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

async def download_youtube_video_quality(
    url: str,
    tmp: Path,
    height: int = 720,
) -> Optional[Path]:
    """Download YouTube video at specific quality"""
    fmt = f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]/best[height<={height}]"
    return await download_youtube_video(url, tmp, fmt=fmt)

async def download_youtube_audio(url: str, tmp: Path, is_music: bool = False, quality: str = "320") -> Optional[Path]:
    """Download YouTube/YT Music audio as MP3"""
    fmt = "bestaudio[ext=m4a]/bestaudio/best"
    layer_fns = [_layer1_opts, _layer2_opts]
    layer_fns.append(_layer3_music_opts if is_music else _layer3_opts)

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

async def download_youtube_audio_192k(url: str, tmp: Path) -> Optional[Path]:
    """Download YouTube audio as 192k MP3 (fast mode)"""
    fmt = "bestaudio[ext=m4a]/bestaudio/best"
    for layer_fn in [_layer1_opts, _layer2_opts, _layer3_opts]:
        opts = layer_fn(tmp, fmt)
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
        opts["postprocessor_args"] = {
            "FFmpegExtractAudio": ["-acodec", "libmp3lame", "-b:a", "192k", "-preset", "ultrafast", "-threads", "4"]
        }
        opts["outtmpl"] = str(tmp / "%(title)s.%(ext)s")
        try:
            with YoutubeDL(opts) as ydl:
                await asyncio.to_thread(lambda: ydl.download([url]))
            mp3_files = list(tmp.glob("*.mp3"))
            if mp3_files:
                return mp3_files[0]
        except Exception as e:
            logger.debug(f"Audio 192k layer failed: {str(e)[:80]}")
    return None

# ─── Ensure video fits Telegram (>50MB fix) ───────────────────────────────────

async def ensure_video_fits_telegram(video_path: Path, tmp_dir: Path) -> Optional[Path]:
    """
    Ensure video fits Telegram 49MB limit.
    Uses dynamic bitrate calculation.
    Falls back to 720p if still too large.
    Never silently fails.
    """
    TG_LIMIT = 49 * 1024 * 1024
    size = get_file_size(video_path)

    if size <= TG_LIMIT:
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
                return remuxed
        return video_path

    logger.info(f"YT VIDEO: {size/1024/1024:.1f}MB exceeds 49MB limit, re-encoding")

    info = await get_video_info(video_path)
    duration = info.get("duration") or 60.0

    # Dynamic bitrate: target 45MB
    target_size_mb = 45
    bitrate = int((target_size_mb * 8 * 1024) / max(duration, 1))
    bitrate = max(bitrate, 300)  # minimum 300kbps

    encoded = tmp_dir / f"enc_{video_path.stem}.mp4"
    args = [
        "-y", "-i", str(video_path),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-b:v", f"{bitrate}k",
        "-maxrate", f"{bitrate}k",
        "-bufsize", f"{bitrate * 2}k",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-threads", "4",
        str(encoded),
    ]
    rc, err = await _run_ffmpeg(args)

    if rc == 0 and encoded.exists():
        enc_size = get_file_size(encoded)
        if enc_size <= TG_LIMIT:
            logger.info(f"YT VIDEO: Re-encoded to {enc_size/1024/1024:.1f}MB")
            return encoded
        logger.warning(f"YT VIDEO: Re-encoded still {enc_size/1024/1024:.1f}MB, trying 720p fallback")

    # Fallback: 720p re-encode
    fallback = tmp_dir / f"fallback_{video_path.stem}.mp4"
    orig_height = info.get("height") or 1080
    target_h = min(orig_height, 720)
    bitrate_720 = int((target_size_mb * 8 * 1024) / max(duration, 1))
    bitrate_720 = max(bitrate_720, 300)

    args_720 = [
        "-y", "-i", str(video_path),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-vf", f"scale=-2:{target_h}",
        "-b:v", f"{bitrate_720}k",
        "-maxrate", f"{bitrate_720}k",
        "-bufsize", f"{bitrate_720 * 2}k",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-threads", "4",
        str(fallback),
    ]
    rc2, err2 = await _run_ffmpeg(args_720)

    if rc2 == 0 and fallback.exists():
        fb_size = get_file_size(fallback)
        logger.info(f"YT VIDEO: 720p fallback {fb_size/1024/1024:.1f}MB")
        return fallback

    logger.error(f"YT VIDEO: Could not compress to fit Telegram limit")
    return video_path  # Return original — let Telegram reject it with proper error

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
        if "message to be replied not found" in err_str or "replied message not found" in err_str:
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
        if "message to be replied not found" in err_str or "replied message not found" in err_str:
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
        if "message to be replied not found" in err_str or "replied message not found" in err_str:
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
    delivered_caption = await format_delivered_with_mention(user_id, first_name)
    _t_start = time.monotonic()

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
                _err = await get_emoji_async("ERROR")
                await _safe_reply_text(
                    m,
                    f"{_err} Unable to process this link.\n\nPlease try again.",
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

            # Log to channel
            _elapsed = time.monotonic() - _t_start
            asyncio.create_task(log_download(
                user=m.from_user,
                link=url,
                chat=m.chat,
                media_type="Audio (YT Music)",
                time_taken=_elapsed,
            ))

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"YT MUSIC ERROR: {e}", exc_info=True)
        await delete_sticker(bot, m.chat.id, sticker_msg_id)
        _err = await get_emoji_async("ERROR")
        await _safe_reply_text(
            m,
            f"{_err} Unable to process this link.\n\nPlease try again.",
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
    delivered_caption = await format_delivered_with_mention(user_id, first_name)
    _t_start = time.monotonic()

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
                _err = await get_emoji_async("ERROR")
                await _safe_reply_text(
                    m,
                    f"{_err} Unable to process this link.\n\nPlease try again.",
                    parse_mode="HTML",
                )
                return

            encoded = tmp / "short_enc.mp4"
            ok = await reencode_shorts(video_file, encoded)
            final = encoded if ok and encoded.exists() else video_file

            # Ensure fits Telegram
            final = await ensure_video_fits_telegram(final, tmp) or final

            info = await get_video_info(final)

            await delete_sticker(bot, m.chat.id, sticker_msg_id)
            sticker_msg_id = None

            sent = await _safe_send_video(
                m.chat.id,
                m.message_id,
                video=FSInputFile(final),
                caption=delivered_caption,
                parse_mode="HTML",
                supports_streaming=True,
                width=info.get("width") or None,
                height=info.get("height") or None,
                duration=int(info.get("duration") or 0) or None,
            )
            if sent and sent.video:
                await url_cache.set(url, "video", sent.video.file_id)

            logger.info(f"SHORTS: Sent to {user_id}")

            # Log to channel
            _elapsed = time.monotonic() - _t_start
            asyncio.create_task(log_download(
                user=m.from_user,
                link=url,
                chat=m.chat,
                media_type="Video (Short)",
                time_taken=_elapsed,
            ))

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"SHORTS ERROR: {e}", exc_info=True)
        await delete_sticker(bot, m.chat.id, sticker_msg_id)
        _err = await get_emoji_async("ERROR")
        await _safe_reply_text(
            m,
            f"{_err} Unable to process this link.\n\nPlease try again.",
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
    _yt = await get_emoji_async("YT")
    try:
        status = await m.reply(
            f"{_yt} <b>𝐂𝐡𝐨𝐨𝐬𝐞 𝐅𝐨𝐫𝐦𝐚𝐭</b>",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "bad request" in err_str:
            try:
                status = await bot.send_message(
                    m.chat.id,
                    f"{_yt} <b>𝐂𝐡𝐨𝐨𝐬𝐞 𝐅𝐨𝐫𝐦𝐚𝐭</b>",
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

    await callback.answer("Preparing video...")

    chat_id = job["chat_id"]
    url = job["url"]
    user_id = job["user_id"]
    first_name = job.get("first_name", "User")
    original_msg_id = job.get("original_msg_id")
    sticker_msg_id = job.get("sticker_msg_id")
    delivered_caption = await format_delivered_with_mention(user_id, first_name)

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
            _err = await get_emoji_async("ERROR")
            await bot.send_message(
                chat_id,
                f"{_err} Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
            return

        if not video_file or not video_file.exists():
            _err = await get_emoji_async("ERROR")
            await bot.send_message(
                chat_id,
                f"{_err} Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
            return

        tmp = job["tmp"]

        # Ensure fits Telegram (>50MB fix)
        final_video = await ensure_video_fits_telegram(video_file, tmp) or video_file

        info = await get_video_info(final_video)
        sent = await _safe_send_video(
            chat_id,
            original_msg_id,
            video=FSInputFile(final_video),
            caption=delivered_caption,
            parse_mode="HTML",
            supports_streaming=True,
            width=info.get("width") or None,
            height=info.get("height") or None,
            duration=int(info.get("duration") or 0) or None,
        )
        if sent and sent.video:
            await url_cache.set(url, "video", sent.video.file_id)

        logger.info(f"YT VIDEO: Sent to {user_id}")

        # Log to channel
        asyncio.create_task(log_download(
            user=type("U", (), {"id": user_id, "first_name": first_name})(),
            link=url,
            chat_type="Group" if job.get("chat_type", "private") not in ("private",) else "Private",
            media_type="Video",
            time_taken=0.0,
        ))

    except Exception as e:
        logger.error(f"YT VIDEO CALLBACK ERROR: {e}", exc_info=True)
        try:
            _err = await get_emoji_async("ERROR")
            await bot.send_message(
                chat_id,
                f"{_err} Unable to process this link.\n\nPlease try again.",
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

    await callback.answer("Preparing audio...")

    chat_id = job["chat_id"]
    url = job["url"]
    user_id = job["user_id"]
    first_name = job.get("first_name", "User")
    original_msg_id = job.get("original_msg_id")
    sticker_msg_id = job.get("sticker_msg_id")
    delivered_caption = await format_delivered_with_mention(user_id, first_name)

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
            _err = await get_emoji_async("ERROR")
            await bot.send_message(
                chat_id,
                f"{_err} Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
            return

        if not audio_file or not audio_file.exists():
            _err = await get_emoji_async("ERROR")
            await bot.send_message(
                chat_id,
                f"{_err} Unable to process this link.\n\nPlease try again.",
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

        # Log to channel
        asyncio.create_task(log_download(
            user=type("U", (), {"id": user_id, "first_name": first_name})(),
            link=url,
            chat_type="Private",
            media_type="Audio",
            time_taken=0.0,
        ))

    except Exception as e:
        logger.error(f"YT AUDIO CALLBACK ERROR: {e}", exc_info=True)
        try:
            _err = await get_emoji_async("ERROR")
            await bot.send_message(
                chat_id,
                f"{_err} Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
        except Exception:
            pass

# ─── YouTube Playlist handler ─────────────────────────────────────────────────

# Semaphore: max 1 concurrent playlist job
_playlist_semaphore = asyncio.Semaphore(1)

# Pending playlist jobs store
_playlist_pending: dict = {}

async def _get_playlist_info(url: str) -> dict:
    """Fetch playlist metadata (name, entries) using yt-dlp"""
    try:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlistend": 200,  # limit to 200 items
            "proxy": config.pick_proxy(),
            "http_headers": {"User-Agent": config.pick_user_agent()},
            "socket_timeout": 30,
        }
        cookie_file = get_random_cookie(config.YT_COOKIES_FOLDER)
        if cookie_file:
            opts["cookiefile"] = cookie_file

        def _extract():
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = await asyncio.to_thread(_extract)
        if not info:
            return {}

        entries = info.get("entries") or []
        title = info.get("title") or info.get("playlist_title") or "Playlist"
        return {"title": title, "entries": entries, "count": len(entries)}
    except Exception as e:
        logger.error(f"YT PLAYLIST INFO ERROR: {e}", exc_info=True)
        return {}


async def handle_youtube_playlist(m: Message, url: str):
    """
    YouTube Playlist handler:
    1. Fetch playlist info
    2. Show mode selector (Audio/Video)
    3. After mode selected → show quality selector
    4. After quality selected → download and send to DM
    """
    user_id = m.from_user.id
    job_key = f"ytpl:{user_id}:{int(time.time())}"

    # Check if user has started bot (needed for DM)
    has_started = await user_state_manager.has_started_bot(user_id)
    if not has_started:
        bot_me = await bot.get_me()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="▶️ Start Bot",
                url=f"https://t.me/{bot_me.username}?start=playlist",
            )
        ]])
        _info = await get_emoji_async("INFO")
        await _safe_reply_text(
            m,
            f"{_info} <b>𝐒𝐭𝐚𝐫𝐭 𝐁𝐨𝐭 𝐅𝐢𝐫𝐬𝐭</b>\n\nStart the bot to receive playlist tracks in DM.\n\nTap below, then resend the playlist link 👇",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    # Fetch playlist info
    _proc = await get_emoji_async("PROCESS")
    try:
        status_msg = await _safe_reply_text(m, f"{_proc} <b>𝐋𝐨𝐚𝐝𝐢𝐧𝐠 𝐏𝐥𝐚𝐲𝐥𝐢𝐬𝐭...</b>", parse_mode="HTML")
    except Exception:
        status_msg = None

    playlist_info = await _get_playlist_info(url)

    if not playlist_info or not playlist_info.get("entries"):
        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass
        _err = await get_emoji_async("ERROR")
        await _safe_reply_text(
            m,
            f"{_err} Unable to process this link.\n\nPlease try again.",
            parse_mode="HTML",
        )
        return

    playlist_name = playlist_info.get("title", "Playlist")[:40]
    entries = playlist_info.get("entries", [])
    total = len(entries)

    # Store playlist job
    _playlist_pending[job_key] = {
        "url": url,
        "playlist_name": playlist_name,
        "entries": entries,
        "total": total,
        "chat_id": m.chat.id,
        "user_id": user_id,
        "first_name": m.from_user.first_name or "User",
        "original_msg_id": m.message_id,
        "created_at": time.time(),
    }

    # Delete loading message
    if status_msg:
        try:
            await status_msg.delete()
        except Exception:
            pass

    # Show mode selector
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎵 Audio", callback_data=f"ytpl_audio:{job_key}"),
        InlineKeyboardButton(text="🎬 Video", callback_data=f"ytpl_video:{job_key}"),
    ]])

    await _safe_reply_text(
        m,
        format_yt_playlist_mode(playlist_name),
        reply_markup=keyboard,
        parse_mode="HTML",
    )

    # Cleanup after 10 minutes
    asyncio.create_task(_cleanup_playlist_pending(job_key, delay=600))


async def _cleanup_playlist_pending(job_key: str, delay: int = 600):
    """Clean up playlist pending job after timeout"""
    await asyncio.sleep(delay)
    _playlist_pending.pop(job_key, None)


@dp.callback_query(lambda c: c.data and c.data.startswith("ytpl_audio:"))
async def cb_ytpl_audio(callback: CallbackQuery):
    """Audio mode selected for playlist"""
    job_key = callback.data.split(":", 1)[1]
    job = _playlist_pending.get(job_key)

    if not job:
        await callback.answer("Session expired. Send the link again.", show_alert=True)
        return

    await callback.answer()

    # Show audio quality selector
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="192k (Fast)", callback_data=f"ytpl_aq:192:{job_key}"),
        InlineKeyboardButton(text="320k (High)", callback_data=f"ytpl_aq:320:{job_key}"),
        InlineKeyboardButton(text="Hi-Res (Best)", callback_data=f"ytpl_aq:hires:{job_key}"),
    ]])

    try:
        await callback.message.edit_text(
            format_yt_audio_quality(),
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    except Exception:
        pass


@dp.callback_query(lambda c: c.data and c.data.startswith("ytpl_video:"))
async def cb_ytpl_video(callback: CallbackQuery):
    """Video mode selected for playlist"""
    job_key = callback.data.split(":", 1)[1]
    job = _playlist_pending.get(job_key)

    if not job:
        await callback.answer("Session expired. Send the link again.", show_alert=True)
        return

    await callback.answer()

    # Show video quality selector
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="360p", callback_data=f"ytpl_vq:360:{job_key}"),
        InlineKeyboardButton(text="480p", callback_data=f"ytpl_vq:480:{job_key}"),
        InlineKeyboardButton(text="720p", callback_data=f"ytpl_vq:720:{job_key}"),
    ]])

    try:
        await callback.message.edit_text(
            format_yt_video_quality(),
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    except Exception:
        pass


@dp.callback_query(lambda c: c.data and c.data.startswith("ytpl_aq:"))
async def cb_ytpl_audio_quality(callback: CallbackQuery):
    """Audio quality selected — start playlist download"""
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Invalid selection.", show_alert=True)
        return

    quality = parts[1]  # "192", "320", or "hires"
    job_key = parts[2]
    job = _playlist_pending.get(job_key)

    if not job:
        await callback.answer("Session expired. Send the link again.", show_alert=True)
        return

    await callback.answer("Starting download...")

    # Delete quality selector message
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Start playlist download in background
    asyncio.create_task(_run_yt_playlist_audio(callback, job_key, job, quality))


@dp.callback_query(lambda c: c.data and c.data.startswith("ytpl_vq:"))
async def cb_ytpl_video_quality(callback: CallbackQuery):
    """Video quality selected — start playlist download"""
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Invalid selection.", show_alert=True)
        return

    height = int(parts[1])  # 360, 480, or 720
    job_key = parts[2]
    job = _playlist_pending.get(job_key)

    if not job:
        await callback.answer("Session expired. Send the link again.", show_alert=True)
        return

    await callback.answer("Starting download...")

    # Delete quality selector message
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Start playlist download in background
    asyncio.create_task(_run_yt_playlist_video(callback, job_key, job, height))


def _bar(pct: int) -> str:
    """Progress bar"""
    width = 10
    filled = int(width * pct / 100)
    return f"[{'█' * filled}{'░' * (width - filled)}] {pct}%"


async def _run_yt_playlist_audio(callback: CallbackQuery, job_key: str, job: dict, quality: str):
    """
    Download YouTube playlist as audio and send to DM.
    """
    async with _playlist_semaphore:
        chat_id = job["chat_id"]
        user_id = job["user_id"]
        playlist_name = job["playlist_name"]
        entries = job["entries"]
        total = len(entries)

        # Send progress message in original chat
        _music = await get_emoji_async("MUSIC")
        try:
            progress_msg = await bot.send_message(
                chat_id,
                f"{_music} <b>𝐏ʟᴀʏʟɪꜱᴛ:</b> {playlist_name}\n\n{_bar(0)}\n0 / {total}",
                parse_mode="HTML",
            )
        except Exception:
            progress_msg = None

        # DM start notification
        try:
            await bot.send_message(
                user_id,
                f"{_music} <b>𝐏ʟᴀʏʟɪꜱᴛ 𝐒𝐭𝐚𝐫𝐭𝐞𝐝</b>\n\n"
                f"<b>{playlist_name}</b>\n"
                f"Tracks: {total}\n\n"
                f"Songs will appear here one by one.",
                parse_mode="HTML",
            )
        except Exception:
            pass

        sent_count = 0
        failed_count = 0

        for i, entry in enumerate(entries):
            if not entry:
                failed_count += 1
                continue

            entry_url = entry.get("url") or entry.get("webpage_url")
            if not entry_url:
                # Try to construct URL from id
                entry_id = entry.get("id")
                if entry_id:
                    entry_url = f"https://www.youtube.com/watch?v={entry_id}"
                else:
                    failed_count += 1
                    continue

            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp = Path(tmp_dir)

                    if quality == "hires":
                        audio_file = await download_youtube_audio(entry_url, tmp, quality="320")
                    elif quality == "320":
                        audio_file = await download_youtube_audio(entry_url, tmp, quality="320")
                    else:  # 192k fast
                        audio_file = await download_youtube_audio_192k(entry_url, tmp)

                    if not audio_file or not audio_file.exists():
                        failed_count += 1
                        logger.warning(f"YT PLAYLIST AUDIO: Track {i+1}/{total} failed")
                    else:
                        try:
                            await bot.send_audio(
                                user_id,
                                FSInputFile(audio_file),
                                title=entry.get("title") or audio_file.stem,
                            )
                            sent_count += 1
                            logger.info(f"YT PLAYLIST AUDIO: Sent {sent_count}/{total}")
                        except TelegramForbiddenError:
                            logger.error(f"User {user_id} blocked bot")
                            break
                        except Exception as e:
                            logger.error(f"YT PLAYLIST AUDIO: Send failed: {e}")
                            failed_count += 1

            except Exception as e:
                logger.error(f"YT PLAYLIST AUDIO: Track {i+1} error: {e}", exc_info=True)
                failed_count += 1

            # Update progress every 5 items
            total_done = sent_count + failed_count
            if progress_msg and (total_done % 5 == 0 or total_done == total):
                pct = min(100, int(total_done * 100 / total)) if total > 0 else 0
                try:
                    await progress_msg.edit_text(
                        f"{_music} <b>𝐏ʟᴀʏʟɪꜱᴛ:</b> {playlist_name}\n\n{_bar(pct)}\n{total_done} / {total}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

        # Show completion
        if progress_msg:
            try:
                await progress_msg.edit_text(
                    await format_yt_playlist_final(playlist_name, total, sent_count, failed_count),
                    parse_mode="HTML",
                )
            except Exception:
                pass

            # Delete after 5 seconds
            async def _del():
                await asyncio.sleep(5)
                try:
                    await progress_msg.delete()
                except Exception:
                    pass
            asyncio.create_task(_del())

        # DM completion
        try:
            _complete = await get_emoji_async("COMPLETE")
            await bot.send_message(
                user_id,
                f"{_complete} <b>𝐏ʟᴀʏʟɪꜱᴛ 𝐃𝐞𝐥𝐢𝐯𝐞𝐫𝐞𝐝</b>\n\n"
                f"<b>{playlist_name}</b>\n"
                f"Sent: {sent_count} / {total}\n\n"
                f"Enjoy your music! {_music}",
                parse_mode="HTML",
            )
        except Exception:
            pass

        logger.info(f"YT PLAYLIST AUDIO: Done — {sent_count} sent, {failed_count} failed")

        # Log to channel
        asyncio.create_task(log_download(
            user=type("U", (), {"id": user_id, "first_name": job.get("first_name", "User")})(),
            link=job.get("url", ""),
            chat_type="Group" if chat_id != user_id else "Private",  # no chat object available here
            media_type=f"Playlist (Audio, {sent_count}/{total})",
            time_taken=0.0,
        ))

        _playlist_pending.pop(job_key, None)


async def _run_yt_playlist_video(callback: CallbackQuery, job_key: str, job: dict, height: int):
    """
    Download YouTube playlist as video and send to DM.
    """
    async with _playlist_semaphore:
        chat_id = job["chat_id"]
        user_id = job["user_id"]
        playlist_name = job["playlist_name"]
        entries = job["entries"]
        total = len(entries)

        # Send progress message in original chat
        _yt = await get_emoji_async("YT")
        try:
            progress_msg = await bot.send_message(
                chat_id,
                f"{_yt} <b>𝐏ʟᴀʏʟɪꜱᴛ:</b> {playlist_name}\n\n{_bar(0)}\n0 / {total}",
                parse_mode="HTML",
            )
        except Exception:
            progress_msg = None

        # DM start notification
        try:
            await bot.send_message(
                user_id,
                f"{_yt} <b>𝐏ʟᴀʏʟɪꜱᴛ 𝐒𝐭𝐚𝐫𝐭𝐞𝐝</b>\n\n"
                f"<b>{playlist_name}</b>\n"
                f"Videos: {total}\n\n"
                f"Videos will appear here one by one.",
                parse_mode="HTML",
            )
        except Exception:
            pass

        sent_count = 0
        failed_count = 0

        for i, entry in enumerate(entries):
            if not entry:
                failed_count += 1
                continue

            entry_url = entry.get("url") or entry.get("webpage_url")
            if not entry_url:
                entry_id = entry.get("id")
                if entry_id:
                    entry_url = f"https://www.youtube.com/watch?v={entry_id}"
                else:
                    failed_count += 1
                    continue

            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp = Path(tmp_dir)

                    video_file = await download_youtube_video_quality(entry_url, tmp, height=height)

                    if not video_file or not video_file.exists():
                        failed_count += 1
                        logger.warning(f"YT PLAYLIST VIDEO: Item {i+1}/{total} failed")
                    else:
                        # Ensure fits Telegram
                        final_video = await ensure_video_fits_telegram(video_file, tmp) or video_file
                        info = await get_video_info(final_video)

                        try:
                            await bot.send_video(
                                user_id,
                                FSInputFile(final_video),
                                title=entry.get("title") or "",
                                supports_streaming=True,
                                width=info.get("width") or None,
                                height=info.get("height") or None,
                                duration=int(info.get("duration") or 0) or None,
                            )
                            sent_count += 1
                            logger.info(f"YT PLAYLIST VIDEO: Sent {sent_count}/{total}")
                        except TelegramForbiddenError:
                            logger.error(f"User {user_id} blocked bot")
                            break
                        except Exception as e:
                            logger.error(f"YT PLAYLIST VIDEO: Send failed: {e}")
                            failed_count += 1

            except Exception as e:
                logger.error(f"YT PLAYLIST VIDEO: Item {i+1} error: {e}", exc_info=True)
                failed_count += 1

            # Update progress every 5 items
            total_done = sent_count + failed_count
            if progress_msg and (total_done % 5 == 0 or total_done == total):
                pct = min(100, int(total_done * 100 / total)) if total > 0 else 0
                try:
                    await progress_msg.edit_text(
                        f"{_yt} <b>𝐏ʟᴀʏʟɪꜱᴛ:</b> {playlist_name}\n\n{_bar(pct)}\n{total_done} / {total}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

        # Show completion
        if progress_msg:
            try:
                await progress_msg.edit_text(
                    await format_yt_playlist_final(playlist_name, total, sent_count, failed_count),
                    parse_mode="HTML",
                )
            except Exception:
                pass

            # Delete after 5 seconds
            async def _del():
                await asyncio.sleep(5)
                try:
                    await progress_msg.delete()
                except Exception:
                    pass
            asyncio.create_task(_del())

        # DM completion
        try:
            _complete = await get_emoji_async("COMPLETE")
            await bot.send_message(
                user_id,
                f"{_complete} <b>𝐏ʟᴀʏʟɪꜱᴛ 𝐃𝐞𝐥𝐢𝐯𝐞𝐫𝐞𝐝</b>\n\n"
                f"<b>{playlist_name}</b>\n"
                f"Sent: {sent_count} / {total}\n\n"
                f"Enjoy your videos! {_yt}",
                parse_mode="HTML",
            )
        except Exception:
            pass

        logger.info(f"YT PLAYLIST VIDEO: Done — {sent_count} sent, {failed_count} failed")

        # Log to channel
        asyncio.create_task(log_download(
            user=type("U", (), {"id": user_id, "first_name": job.get("first_name", "User")})(),
            link=job.get("url", ""),
            chat_type="Group" if chat_id != user_id else "Private",  # no chat object available here
            media_type=f"Playlist (Video, {sent_count}/{total})",
            time_taken=0.0,
        ))

        _playlist_pending.pop(job_key, None)


# ─── Main entry point ─────────────────────────────────────────────────────────

async def handle_youtube(m: Message, url: str):
    """Route YouTube URL to appropriate handler"""
    if not await acquire_user_slot(m.from_user.id, config.MAX_CONCURRENT_PER_USER):
        _proc = await get_emoji_async("PROCESS")
        try:
            await m.reply(f"{_proc} You have downloads in progress. Please wait.", parse_mode="HTML")
        except Exception:
            await bot.send_message(
                m.chat.id,
                f"{_proc} You have downloads in progress. Please wait.",
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
        elif is_youtube_playlist(url):
            await handle_youtube_playlist(m, url)
        else:
            await handle_youtube_normal(m, url)
    finally:
        await release_user_slot(m.from_user.id)
