"""Pinterest downloader - fully async"""
import asyncio
import time
import tempfile
from pathlib import Path
from yt_dlp import YoutubeDL
from aiogram.types import Message, FSInputFile

from core.bot import bot
from core.config import config
from workers.task_queue import download_semaphore
from ui.formatting import format_caption
from utils.helpers import resolve_pin_url
from utils.logger import logger

async def handle_pinterest(m: Message, url: str):
    """Handle Pinterest download request"""
    async with download_semaphore:
        # Resolve shortened URL
        url = await resolve_pin_url(url)
        logger.info(f"PIN: {url}")

        sticker = await bot.send_sticker(m.chat.id, config.PIN_STICKER)
        start = time.perf_counter()

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)
                raw = tmp / "pin.mp4"
                final = tmp / "pinf.mp4"

                opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "format": "best/bestvideo+bestaudio",
                    "merge_output_format": "mp4",
                    "outtmpl": str(raw),
                    "proxy": config.pick_proxy(),
                    "http_headers": {"User-Agent": config.pick_user_agent()},
                    "concurrent_fragment_downloads": 20,
                }

                # Download
                await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))

                # Fast copy with MP4 optimization
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", str(raw),
                    "-c:v", "copy", "-c:a", "copy",
                    "-movflags", "+faststart",
                    str(final),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await proc.wait()

                elapsed = time.perf_counter() - start
                
                # Delete sticker
                try:
                    await bot.delete_message(m.chat.id, sticker.message_id)
                except:
                    pass

                # Send video
                sent = await bot.send_video(
                    m.chat.id,
                    FSInputFile(final),
                    caption=format_caption(m.from_user, elapsed),
                    parse_mode="HTML",
                    supports_streaming=True
                )

                # Pin in groups
                if m.chat.type != "private":
                    try:
                        await bot.pin_chat_message(m.chat.id, sent.message_id)
                    except:
                        pass
                
                logger.info(f"PIN: Done in {elapsed:.2f}s")
                
        except Exception as e:
            logger.error(f"PIN: {e}")
            try:
                await bot.delete_message(m.chat.id, sticker.message_id)
            except:
                pass
            await m.answer(f"❌ 𝐏𝐢𝐧𝐭𝐞𝐫𝐞𝐬𝐭 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}")
