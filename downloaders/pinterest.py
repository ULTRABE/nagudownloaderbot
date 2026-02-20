"""
Pinterest Downloader — Fixed + Clean UI.

Flow:
  1. Resolve pin.it short URLs (HEAD request)
  2. Send sticker (if enabled)
  3. Show: 📌 Fetching Media...
  4. Download with yt-dlp (primary + fallback)
  5. Delete sticker + progress message
  6. Send video — reply to original
  7. Caption: ✓ Delivered — <mention>

Pinterest URL support:
  - pin.it short URLs (expanded via HEAD request)
  - pinterest.com/pin/
  - pinterest.com/video/

Never crash if extraction fails — return clean error.
"""
import asyncio
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
from ui.formatting import format_delivered_with_mention
from ui.stickers import send_sticker, delete_sticker

# ─── URL resolver ─────────────────────────────────────────────────────────────

async def _resolve_pin_url(url: str) -> str:
    """
    Resolve pin.it shortened URL to full Pinterest URL.
    Uses aiohttp HEAD request (non-blocking). Falls back to original on error.
    """
    if "pin.it/" not in url:
        return url
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(
                url,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": config.pick_user_agent()},
            ) as resp:
                resolved = str(resp.url)
                logger.debug(f"Pinterest resolved: {url} → {resolved}")
                return resolved
    except Exception as e:
        logger.debug(f"Pinterest URL resolve failed: {e}")
        # Fallback: try GET redirect
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    allow_redirects=True,
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers={"User-Agent": config.pick_user_agent()},
                ) as resp:
                    return str(resp.url)
        except Exception:
            return url

# ─── Download ─────────────────────────────────────────────────────────────────

async def _download_pinterest(url: str, tmp: Path) -> Optional[Path]:
    """
    Download Pinterest video with yt-dlp.
    Primary attempt: bestvideo+bestaudio merged to mp4.
    Fallback: best single format.
    """
    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(tmp / "%(title)s.%(ext)s"),
        "proxy": config.pick_proxy(),
        "http_headers": {"User-Agent": config.pick_user_agent()},
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "ignoreerrors": False,
    }

    # Primary: merge best video + audio to mp4
    opts_primary = {
        **base_opts,
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }],
    }

    try:
        with YoutubeDL(opts_primary) as ydl:
            await asyncio.to_thread(lambda: ydl.download([url]))
        files = list(tmp.glob("*.mp4")) + list(tmp.glob("*.webm")) + list(tmp.glob("*.mkv"))
        if files:
            return files[0]
    except Exception as e:
        logger.debug(f"Pinterest primary download failed: {type(e).__name__}: {str(e)[:100]}")

    # Fallback: best single format, no merge
    opts_fallback = {
        **base_opts,
        "format": "best[ext=mp4]/best",
    }

    try:
        with YoutubeDL(opts_fallback) as ydl:
            await asyncio.to_thread(lambda: ydl.download([url]))
        files = list(tmp.glob("*.mp4")) + list(tmp.glob("*.webm")) + list(tmp.glob("*.mkv"))
        if files:
            return files[0]
    except Exception as e:
        logger.debug(f"Pinterest fallback download failed: {type(e).__name__}: {str(e)[:100]}")

    return None

# ─── Main handler ─────────────────────────────────────────────────────────────

async def handle_pinterest(m: Message, url: str):
    """
    Download Pinterest video pins.
    Cache-first → download → encode → send.
    Reply to original message with ✓ Delivered — <mention>.
    """
    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    delivered_caption = format_delivered_with_mention(user_id, first_name)

    sticker_msg_id = None

    # Resolve shortened URL first
    if "pin.it/" in url:
        url = await _resolve_pin_url(url)
        logger.info(f"PINTEREST: Resolved to {url}")

    # Cache check
    cached = await url_cache.get(url, "video")
    if cached:
        try:
            await bot.send_video(
                m.chat.id,
                cached,
                caption=delivered_caption,
                parse_mode="HTML",
                reply_to_message_id=m.message_id,
                supports_streaming=True,
            )
            return
        except Exception:
            pass  # Stale cache — fall through

    async with download_semaphore:
        logger.info(f"PINTEREST: {url}")

        # Send sticker
        sticker_msg_id = await send_sticker(bot, m.chat.id, "pinterest")

        # Processing message
        status = await m.reply("📌 Fetching Media...", parse_mode="HTML")

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)

                # Animate progress
                async def _animate():
                    await asyncio.sleep(2)
                    try:
                        await status.edit_text(
                            "Optimizing for fast delivery...",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

                anim_task = asyncio.create_task(_animate())

                video_file = await _download_pinterest(url, tmp)
                anim_task.cancel()

                if not video_file:
                    await delete_sticker(bot, m.chat.id, sticker_msg_id)
                    sticker_msg_id = None
                    await status.delete()
                    await m.reply(
                        "⚠ Unable to process this link.\n\nPlease try again.",
                        parse_mode="HTML",
                    )
                    return

                # Smart encode: stream copy if compatible, else adaptive
                encoded = tmp / "pin_enc.mp4"
                ok = await instagram_smart_encode(video_file, encoded)
                final = encoded if ok and encoded.exists() else video_file

                parts = await ensure_fits_telegram(final, tmp)

                # Delete sticker + progress
                await delete_sticker(bot, m.chat.id, sticker_msg_id)
                sticker_msg_id = None
                await status.delete()

                for i, part in enumerate(parts):
                    info = await get_video_info(part)
                    cap = delivered_caption if i == len(parts) - 1 else f"Part {i+1}/{len(parts)}"
                    sent = await bot.send_video(
                        m.chat.id,
                        FSInputFile(part),
                        caption=cap,
                        parse_mode="HTML",
                        reply_to_message_id=m.message_id,
                        supports_streaming=True,
                        width=info.get("width") or None,
                        height=info.get("height") or None,
                        duration=int(info.get("duration") or 0) or None,
                    )
                    if sent and sent.video and len(parts) == 1:
                        await url_cache.set(url, "video", sent.video.file_id)

                logger.info(f"PINTEREST: Sent {len(parts)} file(s) to {user_id}")

        except Exception as e:
            logger.error(f"PINTEREST ERROR: {e}")
            await delete_sticker(bot, m.chat.id, sticker_msg_id)
            sticker_msg_id = None
            try:
                await status.delete()
            except Exception:
                pass
            await m.reply(
                "⚠ Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
        finally:
            if sticker_msg_id:
                await delete_sticker(bot, m.chat.id, sticker_msg_id)
