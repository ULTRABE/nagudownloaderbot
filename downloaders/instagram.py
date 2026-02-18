"""
Instagram Downloader — Fast delivery with cache + smart encode.

Flow:
  1. Cache check (SHA256 → file_id) → send instantly if hit
  2. Show progress bar
  3. Layered extraction: API → mobile UA → cookies (skip if folder missing)
  4. Stream copy if H.264/AAC + small enough
  5. Else adaptive encode (veryfast, target 4–6MB)
  6. Send as video (NOT document) with metadata
  7. Reply to original with ✓ Delivered
  8. Delete progress message
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
from utils.cache import url_cache
from utils.media_processor import (
    ensure_fits_telegram, instagram_smart_encode,
    get_video_info,
)
from utils.watchdog import acquire_user_slot, release_user_slot
from ui.formatting import format_delivered, mono

# ─── Progress bar ─────────────────────────────────────────────────────────────

def _progress(pct: int, label: str = "Downloading") -> str:
    width = 10
    filled = int(width * pct / 100)
    bar = "▓" * filled + "░" * (width - filled)
    return f"<code>  [{bar}]  {pct}%  {label}</code>"

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
    # Try Instagram-specific cookies
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

# ─── Main handler ─────────────────────────────────────────────────────────────

async def handle_instagram(m: Message, url: str):
    """
    Download Instagram posts, reels, stories.
    Cache-first → stream copy → adaptive encode.
    Reply to original message with ✓ Delivered.
    """
    if not await acquire_user_slot(m.from_user.id, config.MAX_CONCURRENT_PER_USER):
        await m.reply(mono("  ⏳  You have downloads in progress. Please wait."))
        return

    try:
        # Cache check
        cached = await url_cache.get(url, "video")
        if cached:
            try:
                sent = await m.reply_video(cached, supports_streaming=True)
                await m.reply(format_delivered())
                return
            except Exception:
                pass  # Stale cache — fall through

        async with download_semaphore:
            logger.info(f"INSTAGRAM: {url}")

            status = await m.reply(_progress(0, "Downloading"), parse_mode="HTML")

            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp = Path(tmp_dir)

                    # Animate progress
                    async def _animate():
                        for pct in (20, 50, 80):
                            await asyncio.sleep(1.5)
                            try:
                                await status.edit_text(
                                    _progress(pct, "Downloading"), parse_mode="HTML"
                                )
                            except Exception:
                                pass

                    anim_task = asyncio.create_task(_animate())

                    video_file = await download_instagram(url, tmp)
                    anim_task.cancel()

                    if not video_file:
                        await status.delete()
                        await m.reply(mono("  ✗  Could not process this link"))
                        return

                    try:
                        await status.edit_text(_progress(90, "Encoding"), parse_mode="HTML")
                    except Exception:
                        pass

                    # Smart encode: stream copy if compatible, else adaptive
                    encoded = tmp / "ig_enc.mp4"
                    ok = await instagram_smart_encode(video_file, encoded)
                    final = encoded if ok and encoded.exists() else video_file

                    parts = await ensure_fits_telegram(final, tmp)

                    await status.delete()

                    for i, part in enumerate(parts):
                        info = await get_video_info(part)
                        caption = f"Part {i+1}/{len(parts)}" if len(parts) > 1 else None
                        sent = await m.reply_video(
                            FSInputFile(part),
                            caption=caption,
                            supports_streaming=True,
                            width=info.get("width") or None,
                            height=info.get("height") or None,
                            duration=int(info.get("duration") or 0) or None,
                        )
                        # Cache single-part result
                        if sent and sent.video and len(parts) == 1:
                            await url_cache.set(url, "video", sent.video.file_id)

                    await m.reply(format_delivered())
                    logger.info(f"INSTAGRAM: Sent {len(parts)} file(s) to {m.from_user.id}")

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"INSTAGRAM ERROR: {e}")
                try:
                    await status.delete()
                except Exception:
                    pass
                await m.reply(mono("  ✗  Could not process this link"))

    finally:
        await release_user_slot(m.from_user.id)
