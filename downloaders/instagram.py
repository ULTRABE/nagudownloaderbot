"""
Instagram Downloader — Fast delivery with cache + smart encode.

Flow:
  1. Send sticker (if enabled)
  2. Show: ⚡ Fetching Media...
  3. Download with layered extraction
  4. Delete sticker + progress message
  5. Send video — reply to original
  6. Caption: ✓ Delivered — <mention>
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

# ─── Main handler ─────────────────────────────────────────────────────────────

async def handle_instagram(m: Message, url: str):
    """
    Download Instagram posts, reels, stories.
    Cache-first → stream copy → adaptive encode.
    Reply to original message with ✓ Delivered — <mention>.
    """
    if not await acquire_user_slot(m.from_user.id, config.MAX_CONCURRENT_PER_USER):
        await m.reply("⏳ You have downloads in progress. Please wait.", parse_mode="HTML")
        return

    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    delivered_caption = format_delivered_with_mention(user_id, first_name)

    sticker_msg_id = None

    try:
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
            logger.info(f"INSTAGRAM: {url}")

            # Send sticker
            sticker_msg_id = await send_sticker(bot, m.chat.id, "instagram")

            # Processing message
            status = await m.reply("⚡ Fetching Media...", parse_mode="HTML")

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

                    video_file = await download_instagram(url, tmp)
                    anim_task.cancel()

                    if not video_file:
                        await delete_sticker(bot, m.chat.id, sticker_msg_id)
                        await status.delete()
                        await m.reply(
                            "⚠ Unable to process this link.\n\nPlease try again.",
                            parse_mode="HTML",
                        )
                        return

                    # Smart encode
                    encoded = tmp / "ig_enc.mp4"
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
                        # Cache single-part result
                        if sent and sent.video and len(parts) == 1:
                            await url_cache.set(url, "video", sent.video.file_id)

                    logger.info(f"INSTAGRAM: Sent {len(parts)} file(s) to {user_id}")

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"INSTAGRAM ERROR: {e}")
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
        await release_user_slot(m.from_user.id)
        if sticker_msg_id:
            await delete_sticker(bot, m.chat.id, sticker_msg_id)
