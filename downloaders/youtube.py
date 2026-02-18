"""
YouTube downloader — layered extraction (API → alt config → cookies),
Shorts detection with re-encode, inline Video/Audio buttons for normal videos,
YT Music support (music.youtube.com → 320kbps audio).

Video preview fix:
  - Always output MP4 with -movflags +faststart
  - Include duration, width, height metadata in send_video call
  - Never send as document
"""
import asyncio
import time
import tempfile
import re
from pathlib import Path
from typing import Optional, Tuple

from yt_dlp import YoutubeDL
from aiogram.types import (
    Message, FSInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
)
from aiogram.exceptions import TelegramBadRequest

from core.bot import bot, dp
from core.config import config
from workers.task_queue import download_semaphore
from utils.helpers import get_random_cookie
from utils.logger import logger
from utils.media_processor import (
    reencode_shorts, ensure_fits_telegram, extract_audio_from_video,
    get_video_info, get_file_size,
)
from utils.watchdog import (
    make_job_id, register_job, finish_job,
    mark_url_processing, clear_url_processing,
    acquire_user_slot, release_user_slot,
)

# ─── URL detection ────────────────────────────────────────────────────────────

def is_youtube_short(url: str) -> bool:
    """Detect YouTube Shorts URL"""
    return "/shorts/" in url.lower()

def is_youtube_music(url: str) -> bool:
    """Detect YouTube Music URL"""
    return "music.youtube.com" in url.lower()

# ─── Layered yt-dlp extraction ────────────────────────────────────────────────

def _base_opts(tmp: Path) -> dict:
    """Common yt-dlp options"""
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

def _layer1_opts(tmp: Path, format_str: str) -> dict:
    """Layer 1: Standard API extraction, best quality"""
    opts = _base_opts(tmp)
    opts["format"] = format_str
    return opts

def _layer2_opts(tmp: Path, format_str: str) -> dict:
    """Layer 2: Alternative extractor config (Android + Web clients)"""
    opts = _base_opts(tmp)
    opts["format"] = format_str
    opts["extractor_args"] = {"youtube": {"player_client": ["android", "web"]}}
    opts["http_headers"]["User-Agent"] = (
        "com.google.android.youtube/17.36.4 (Linux; U; Android 12) gzip"
    )
    return opts

def _layer3_opts(tmp: Path, format_str: str) -> dict:
    """Layer 3: Cookie-based fallback"""
    opts = _base_opts(tmp)
    opts["format"] = format_str
    cookie_file = get_random_cookie(config.YT_COOKIES_FOLDER)
    if cookie_file:
        opts["cookiefile"] = cookie_file
    return opts

def _layer3_music_opts(tmp: Path, format_str: str) -> dict:
    """Layer 3 for YT Music: use YT Music cookies folder"""
    opts = _base_opts(tmp)
    opts["format"] = format_str
    cookie_file = get_random_cookie(config.YT_MUSIC_COOKIES_FOLDER)
    if cookie_file:
        opts["cookiefile"] = cookie_file
    return opts

async def _try_download(url: str, opts: dict) -> Optional[Path]:
    """
    Attempt yt-dlp download with given options.
    Returns path to downloaded file or None on failure.
    """
    outtmpl = opts["outtmpl"]
    tmp = Path(outtmpl).parent

    try:
        with YoutubeDL(opts) as ydl:
            await asyncio.to_thread(lambda: ydl.download([url]))

        files = (
            list(tmp.glob("*.mp4")) +
            list(tmp.glob("*.webm")) +
            list(tmp.glob("*.mkv")) +
            list(tmp.glob("*.m4v"))
        )
        return files[0] if files else None
    except Exception as e:
        logger.debug(f"yt-dlp layer failed: {type(e).__name__}: {str(e)[:100]}")
        return None

async def download_youtube_video(
    url: str,
    tmp: Path,
    format_str: str = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
) -> Optional[Path]:
    """
    Download YouTube video using layered extraction.
    Tries 3 layers silently, returns file path or None.
    """
    for layer_fn in [_layer1_opts, _layer2_opts, _layer3_opts]:
        opts = layer_fn(tmp, format_str)
        result = await _try_download(url, opts)
        if result:
            return result
    return None

async def download_youtube_audio(url: str, tmp: Path, is_music: bool = False) -> Optional[Path]:
    """
    Download YouTube/YT Music audio (best quality MP3) using layered extraction.
    """
    format_str = "bestaudio[ext=m4a]/bestaudio/best"

    layer_fns = [_layer1_opts, _layer2_opts]
    if is_music:
        layer_fns.append(_layer3_music_opts)
    else:
        layer_fns.append(_layer3_opts)

    for layer_fn in layer_fns:
        opts = layer_fn(tmp, format_str)
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

# ─── Pending download cache (for inline button flow) ─────────────────────────
_pending: dict = {}

# ─── YT Music handler ────────────────────────────────────────────────────────

async def handle_youtube_music(m: Message, url: str):
    """
    Handle YouTube Music URL.
    Extracts audio stream, converts to 320kbps MP3, embeds metadata, sends as audio.
    """
    sticker = await bot.send_sticker(m.chat.id, config.YT_STICKER)
    start_time = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            audio_file = await download_youtube_audio(url, tmp, is_music=True)

            if not audio_file:
                await bot.delete_message(m.chat.id, sticker.message_id)
                await m.answer("Could not process this link.")
                return

            elapsed = time.perf_counter() - start_time
            await bot.delete_message(m.chat.id, sticker.message_id)

            await bot.send_audio(
                m.chat.id,
                FSInputFile(audio_file),
            )

            logger.info(f"YT MUSIC: Sent in {elapsed:.2f}s")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"YT MUSIC ERROR: {e}")
        try:
            await bot.delete_message(m.chat.id, sticker.message_id)
        except Exception:
            pass
        await m.answer("Could not process this link.")

# ─── Shorts handler ───────────────────────────────────────────────────────────

async def handle_youtube_short(m: Message, url: str):
    """Handle YouTube Shorts — download, re-encode for quality, send as video with preview"""
    sticker = await bot.send_sticker(m.chat.id, config.YT_STICKER)
    start_time = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            video_file = await download_youtube_video(
                url, tmp,
                format_str="bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            )

            if not video_file:
                await bot.delete_message(m.chat.id, sticker.message_id)
                await m.answer("Could not process this link.")
                return

            # Re-encode for quality + Telegram preview compatibility
            encoded = tmp / "short_encoded.mp4"
            encode_ok = await reencode_shorts(video_file, encoded)
            final_file = encoded if encode_ok and encoded.exists() else video_file

            # Get video metadata for send_video call
            info = await get_video_info(final_file)
            width = info.get("width") or 1080
            height = info.get("height") or 1920
            duration = int(info.get("duration") or 0)

            # Handle Telegram size limit
            parts = await ensure_fits_telegram(final_file, tmp)

            elapsed = time.perf_counter() - start_time
            await bot.delete_message(m.chat.id, sticker.message_id)

            for part in parts:
                part_info = await get_video_info(part)
                await bot.send_video(
                    m.chat.id,
                    FSInputFile(part),
                    supports_streaming=True,
                    width=part_info.get("width") or width,
                    height=part_info.get("height") or height,
                    duration=int(part_info.get("duration") or duration),
                )

            logger.info(f"SHORTS: Sent in {elapsed:.2f}s")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"SHORTS ERROR: {e}")
        try:
            await bot.delete_message(m.chat.id, sticker.message_id)
        except Exception:
            pass
        await m.answer("Could not process this link.")

# ─── Normal video handler ─────────────────────────────────────────────────────

async def handle_youtube_normal(m: Message, url: str):
    """
    Handle normal YouTube video.
    Shows inline Video/Audio buttons immediately.
    Downloads 1080p video + 320kbps audio in background.
    Sends when user taps button (waits if still downloading).
    """
    job_key = f"yt:{m.from_user.id}:{int(time.time())}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎥 Video", callback_data=f"yt_video:{job_key}"),
        InlineKeyboardButton(text="🎧 Audio", callback_data=f"yt_audio:{job_key}"),
    ]])

    prompt = await m.answer(
        "⬇️ Choose format:",
        reply_markup=keyboard,
    )

    # Start background downloads
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
        "user_id": m.from_user.id,
        "prompt_id": prompt.message_id,
        "created_at": time.time(),
    }

    asyncio.create_task(_bg_download_video(job_key, url, tmp, video_future))
    asyncio.create_task(_bg_download_audio(job_key, url, tmp, audio_future))
    asyncio.create_task(_cleanup_pending(job_key, delay=600))

async def _bg_download_video(job_key: str, url: str, tmp: Path, future: asyncio.Future):
    """Background video download task"""
    try:
        async with download_semaphore:
            video_file = await download_youtube_video(
                url, tmp,
                format_str="bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
            )
            if not future.done():
                future.set_result(video_file)
    except Exception as e:
        logger.error(f"BG video download error: {e}")
        if not future.done():
            future.set_result(None)

async def _bg_download_audio(job_key: str, url: str, tmp: Path, future: asyncio.Future):
    """Background audio download task"""
    try:
        async with download_semaphore:
            audio_file = await download_youtube_audio(url, tmp)
            if not future.done():
                future.set_result(audio_file)
    except Exception as e:
        logger.error(f"BG audio download error: {e}")
        if not future.done():
            future.set_result(None)

async def _cleanup_pending(job_key: str, delay: int = 600):
    """Clean up pending job after delay"""
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
    """Handle Video button tap"""
    job_key = callback.data.split(":", 1)[1]
    job = _pending.get(job_key)

    if not job:
        await callback.answer("Session expired. Please send the link again.", show_alert=True)
        return

    await callback.answer("⏳ Preparing video...")

    try:
        # Delete the button message
        try:
            await bot.delete_message(job["chat_id"], job["prompt_id"])
        except Exception:
            pass

        sticker = await bot.send_sticker(job["chat_id"], config.YT_STICKER)
        start_time = time.perf_counter()

        try:
            video_file = await asyncio.wait_for(
                asyncio.shield(job["video_future"]),
                timeout=config.DOWNLOAD_TIMEOUT,
            )
        except asyncio.TimeoutError:
            try:
                await bot.delete_message(job["chat_id"], sticker.message_id)
            except Exception:
                pass
            await bot.send_message(job["chat_id"], "Could not process this link.")
            return

        try:
            await bot.delete_message(job["chat_id"], sticker.message_id)
        except Exception:
            pass

        if not video_file or not video_file.exists():
            await bot.send_message(job["chat_id"], "Could not process this link.")
            return

        tmp = job["tmp"]
        parts = await ensure_fits_telegram(video_file, tmp)
        elapsed = time.perf_counter() - start_time

        for i, part in enumerate(parts):
            # Get metadata for proper Telegram video preview
            info = await get_video_info(part)
            caption = f"Part {i+1}/{len(parts)}" if len(parts) > 1 else None
            await bot.send_video(
                job["chat_id"],
                FSInputFile(part),
                caption=caption,
                supports_streaming=True,
                width=info.get("width") or None,
                height=info.get("height") or None,
                duration=int(info.get("duration") or 0) or None,
            )

        logger.info(f"YT VIDEO: Sent {len(parts)} part(s) in {elapsed:.2f}s")

    except Exception as e:
        logger.error(f"YT VIDEO CALLBACK ERROR: {e}")
        try:
            await bot.send_message(job["chat_id"], "Could not process this link.")
        except Exception:
            pass

@dp.callback_query(lambda c: c.data and c.data.startswith("yt_audio:"))
async def cb_yt_audio(callback: CallbackQuery):
    """Handle Audio button tap"""
    job_key = callback.data.split(":", 1)[1]
    job = _pending.get(job_key)

    if not job:
        await callback.answer("Session expired. Please send the link again.", show_alert=True)
        return

    await callback.answer("⏳ Preparing audio...")

    try:
        try:
            await bot.delete_message(job["chat_id"], job["prompt_id"])
        except Exception:
            pass

        sticker = await bot.send_sticker(job["chat_id"], config.YT_STICKER)
        start_time = time.perf_counter()

        try:
            audio_file = await asyncio.wait_for(
                asyncio.shield(job["audio_future"]),
                timeout=config.DOWNLOAD_TIMEOUT,
            )
        except asyncio.TimeoutError:
            try:
                await bot.delete_message(job["chat_id"], sticker.message_id)
            except Exception:
                pass
            await bot.send_message(job["chat_id"], "Could not process this link.")
            return

        try:
            await bot.delete_message(job["chat_id"], sticker.message_id)
        except Exception:
            pass

        if not audio_file or not audio_file.exists():
            await bot.send_message(job["chat_id"], "Could not process this link.")
            return

        elapsed = time.perf_counter() - start_time

        await bot.send_audio(
            job["chat_id"],
            FSInputFile(audio_file),
        )

        logger.info(f"YT AUDIO: Sent in {elapsed:.2f}s")

    except Exception as e:
        logger.error(f"YT AUDIO CALLBACK ERROR: {e}")
        try:
            await bot.send_message(job["chat_id"], "Could not process this link.")
        except Exception:
            pass

# ─── Main entry point ─────────────────────────────────────────────────────────

async def handle_youtube(m: Message, url: str):
    """
    Route YouTube URL to appropriate handler:
    - music.youtube.com → audio extraction (320kbps MP3)
    - /shorts/ → direct download + re-encode
    - Normal → inline buttons + background download
    """
    if not await acquire_user_slot(m.from_user.id, config.MAX_CONCURRENT_PER_USER):
        await m.answer("⏳ You already have downloads in progress. Please wait.")
        return

    try:
        if is_youtube_music(url):
            logger.info(f"YOUTUBE MUSIC: {url}")
            await handle_youtube_music(m, url)
        elif is_youtube_short(url):
            logger.info(f"YOUTUBE SHORTS: {url}")
            await handle_youtube_short(m, url)
        else:
            logger.info(f"YOUTUBE NORMAL: {url}")
            await handle_youtube_normal(m, url)
    finally:
        await release_user_slot(m.from_user.id)
