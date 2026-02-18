"""
Pinterest Downloader — Fast delivery with cache + smart encode.

Flow:
  1. Cache check → send instantly if hit
  2. Resolve pin.it shortened URLs (async, no blocking subprocess)
  3. Show progress bar
  4. Download with yt-dlp
  5. Stream copy if H.264/AAC + small
  6. Else adaptive encode (veryfast, target 4–6MB)
  7. Send as video with metadata
  8. Reply to original with ✓ Delivered
  9. Delete progress message
"""
import asyncio
import time
import tempfile
from pathlib import Path
from typing import Optional

import aiohttp
from yt_dlp import YoutubeDL
from aiogram.types import Message, FSInputFile

from core.bot import bot
from core.config import config
from workers.task_queue import download_semaphore
from utils.logger import logger
from utils.cache import url_cache
from utils.media_processor import (
    ensure_fits_telegram, instagram_smart_encode,
    get_video_info,
)
from ui.formatting import format_delivered, mono

# ─── Progress bar ─────────────────────────────────────────────────────────────

def _progress(pct: int, label: str = "Downloading") -> str:
    width = 10
    filled = int(width * pct / 100)
    bar = "▓" * filled + "░" * (width - filled)
    return f"<code>  [{bar}]  {pct}%  {label}</code>"

# ─── URL resolver ─────────────────────────────────────────────────────────────

async def _resolve_pin_url(url: str) -> str:
    """
    Resolve pin.it shortened URL to full Pinterest URL.
    Uses aiohttp (non-blocking). Falls back to original on error.
    """
    if "pin.it/" not in url:
        return url
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": config.pick_user_agent()},
            ) as resp:
                return str(resp.url)
    except Exception as e:
        logger.debug(f"Pinterest URL resolve failed: {e}")
        return url

# ─── Download ─────────────────────────────────────────────────────────────────

async def _download_pinterest(url: str, tmp: Path) -> Optional[Path]:
    """Download Pinterest video with yt-dlp"""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(tmp / "%(title)s.%(ext)s"),
        "proxy": config.pick_proxy(),
        "http_headers": {"User-Agent": config.pick_user_agent()},
        "socket_timeout": 30,
        "retries": 3,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    }
    try:
        with YoutubeDL(opts) as ydl:
            await asyncio.to_thread(lambda: ydl.download([url]))
        files = list(tmp.glob("*.mp4")) + list(tmp.glob("*.webm"))
        return files[0] if files else None
    except Exception as e:
        logger.debug(f"Pinterest download failed: {e}")
        return None

# ─── Main handler ─────────────────────────────────────────────────────────────

async def handle_pinterest(m: Message, url: str):
    """
    Download Pinterest video pins.
    Cache-first → stream copy → adaptive encode.
    Reply to original with ✓ Delivered.
    """
    # Resolve shortened URL first
    if "pin.it/" in url:
        url = await _resolve_pin_url(url)
        logger.info(f"PINTEREST: Resolved to {url}")

    # Cache check
    cached = await url_cache.get(url, "video")
    if cached:
        try:
            sent = await m.reply_video(cached, supports_streaming=True)
            await m.reply(format_delivered())
            return
        except Exception:
            pass

    async with download_semaphore:
        logger.info(f"PINTEREST: {url}")

        status = await m.reply(_progress(0, "Downloading"), parse_mode="HTML")

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)

                # Animate progress
                async def _animate():
                    for pct in (25, 55, 80):
                        await asyncio.sleep(1.5)
                        try:
                            await status.edit_text(
                                _progress(pct, "Downloading"), parse_mode="HTML"
                            )
                        except Exception:
                            pass

                anim_task = asyncio.create_task(_animate())

                video_file = await _download_pinterest(url, tmp)
                anim_task.cancel()

                if not video_file:
                    await status.delete()
                    await m.reply(mono("  ✗  No video found at this URL"))
                    return

                try:
                    await status.edit_text(_progress(90, "Encoding"), parse_mode="HTML")
                except Exception:
                    pass

                # Smart encode: stream copy if compatible, else adaptive
                encoded = tmp / "pin_enc.mp4"
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
                    if sent and sent.video and len(parts) == 1:
                        await url_cache.set(url, "video", sent.video.file_id)

                await m.reply(format_delivered())
                logger.info(f"PINTEREST: Sent {len(parts)} file(s) to {m.from_user.id}")

        except Exception as e:
            logger.error(f"PINTEREST ERROR: {e}")
            try:
                await status.delete()
            except Exception:
                pass
            await m.reply(mono("  ✗  Pinterest download failed"))
