"""
Instagram downloader — layered extraction (API → alt config → cookies),
stream copy if H.264/AAC, re-encode only if needed, highest quality.
"""
import asyncio
import glob
import time
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
from utils.media_processor import ensure_fits_telegram, instagram_smart_encode, get_file_size
from utils.watchdog import acquire_user_slot, release_user_slot

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
        # Prefer MP4 natively to avoid re-encode
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    }

def _layer1_opts(tmp: Path) -> dict:
    """Layer 1: Standard API extraction"""
    return _base_opts(tmp)

def _layer2_opts(tmp: Path) -> dict:
    """Layer 2: Alternative user-agent (mobile Instagram)"""
    opts = _base_opts(tmp)
    opts["http_headers"]["User-Agent"] = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram/303.0"
    )
    return opts

def _layer3_opts(tmp: Path) -> dict:
    """Layer 3: Cookie-based fallback"""
    opts = _base_opts(tmp)
    ig_cookies = (
        glob.glob("cookies_instagram*.txt") +
        [f for f in glob.glob("*.txt") if "instagram" in f.lower()]
    )
    if ig_cookies:
        opts["cookiefile"] = ig_cookies[0]
    return opts

async def _try_download(url: str, opts: dict) -> Optional[Path]:
    """Attempt download with given options, return file path or None"""
    tmp = Path(opts["outtmpl"]).parent

    try:
        with YoutubeDL(opts) as ydl:
            await asyncio.to_thread(lambda: ydl.download([url]))

        files = (
            list(tmp.glob("*.mp4")) +
            list(tmp.glob("*.webm")) +
            list(tmp.glob("*.mov")) +
            list(tmp.glob("*.mkv"))
        )
        return files[0] if files else None
    except Exception as e:
        logger.debug(f"IG layer failed: {type(e).__name__}: {str(e)[:80]}")
        return None

async def download_instagram(url: str, tmp: Path) -> Optional[Path]:
    """
    Download Instagram content using layered extraction.
    Tries 3 layers silently.
    """
    for layer_fn in [_layer1_opts, _layer2_opts, _layer3_opts]:
        opts = layer_fn(tmp)
        result = await _try_download(url, opts)
        if result:
            return result
    return None

# ─── Main handler ─────────────────────────────────────────────────────────────

async def handle_instagram(m: Message, url: str):
    """
    Download Instagram posts, reels, stories.
    - Layered extraction (3 layers)
    - Stream copy if already H.264/AAC (fast, no quality loss)
    - Re-encode only if needed (preserves FPS and sharpness)
    - Handles Telegram size limits automatically
    """
    if not await acquire_user_slot(m.from_user.id, config.MAX_CONCURRENT_PER_USER):
        await m.answer("⏳ You already have downloads in progress. Please wait.")
        return

    try:
        async with download_semaphore:
            logger.info(f"INSTAGRAM: {url}")

            sticker = await bot.send_sticker(m.chat.id, config.IG_STICKER)
            start_time = time.perf_counter()

            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp = Path(tmp_dir)

                    video_file = await download_instagram(url, tmp)

                    if not video_file:
                        await bot.delete_message(m.chat.id, sticker.message_id)
                        await m.answer("Could not process this link.")
                        return

                    # Smart encode: stream copy if H.264/AAC, else re-encode
                    encoded = tmp / f"ig_encoded.mp4"
                    encode_ok = await instagram_smart_encode(video_file, encoded)
                    final_file = encoded if encode_ok and encoded.exists() else video_file

                    elapsed = time.perf_counter() - start_time
                    await bot.delete_message(m.chat.id, sticker.message_id)

                    # Handle Telegram size limits
                    parts = await ensure_fits_telegram(final_file, tmp)

                    for i, part in enumerate(parts):
                        caption = f"Part {i+1}/{len(parts)}" if len(parts) > 1 else None
                        await bot.send_video(
                            m.chat.id,
                            FSInputFile(part),
                            caption=caption,
                            supports_streaming=True,
                        )

                    logger.info(f"INSTAGRAM: Sent {len(parts)} file(s) in {elapsed:.2f}s")

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"INSTAGRAM ERROR: {e}")
                try:
                    await bot.delete_message(m.chat.id, sticker.message_id)
                except Exception:
                    pass
                await m.answer("Could not process this link.")
    finally:
        await release_user_slot(m.from_user.id)
