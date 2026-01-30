"""Pinterest downloader - Fully async with URL resolution"""
import asyncio
import time
import tempfile
from pathlib import Path
from yt_dlp import YoutubeDL
from aiogram.types import Message, FSInputFile

from core.bot import bot
from core.config import config
from workers.task_queue import download_semaphore
from ui.formatting import format_download_complete
from utils.helpers import resolve_pinterest_url
from utils.logger import logger

async def handle_pinterest(m: Message, url: str):
    """
    Download Pinterest video pins
    Resolves shortened pin.it URLs
    """
    async with download_semaphore:
        logger.info(f"PINTEREST: {url}")
        
        # Resolve shortened URLs
        if "pin.it/" in url:
            url = await asyncio.to_thread(resolve_pinterest_url, url)
            logger.info(f"PINTEREST: Resolved to {url}")
        
        # Send sticker as progress indicator
        sticker = await bot.send_sticker(m.chat.id, config.PIN_STICKER)
        start_time = time.perf_counter()
        
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)
                
                # yt-dlp options for Pinterest
                opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "outtmpl": str(tmp / "%(title)s.%(ext)s"),
                    "proxy": config.pick_proxy(),
                    "http_headers": {
                        "User-Agent": config.pick_user_agent()
                    },
                    "socket_timeout": 30,
                    "retries": 3
                }
                
                # Download asynchronously
                with YoutubeDL(opts) as ydl:
                    await asyncio.to_thread(
                        lambda: ydl.download([url])
                    )
                
                # Find downloaded files
                video_files = list(tmp.glob("*.mp4")) + list(tmp.glob("*.webm"))
                
                if not video_files:
                    await bot.delete_message(m.chat.id, sticker.message_id)
                    await m.answer("No video found")
                    return
                
                elapsed = time.perf_counter() - start_time
                
                # Delete sticker
                await bot.delete_message(m.chat.id, sticker.message_id)
                
                # Send video
                await bot.send_video(
                    m.chat.id,
                    FSInputFile(video_files[0]),
                    caption=format_download_complete(m.from_user, elapsed, "Pinterest"),
                    parse_mode="HTML"
                )
                
                logger.info(f"PINTEREST: Sent video in {elapsed:.2f}s")
        
        except Exception as e:
            logger.error(f"PINTEREST ERROR: {e}")
            try:
                await bot.delete_message(m.chat.id, sticker.message_id)
            except:
                pass
            await m.answer(f"Pinterest download failed\n{str(e)[:100]}")
