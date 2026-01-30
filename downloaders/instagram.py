"""Instagram downloader - Fully async with proper error handling"""
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
from utils.helpers import get_random_cookie
from utils.logger import logger

async def handle_instagram(m: Message, url: str):
    """
    Download Instagram posts, reels, stories
    Fully async implementation
    """
    async with download_semaphore:
        logger.info(f"INSTAGRAM: {url}")
        
        # Send sticker as progress indicator
        sticker = await bot.send_sticker(m.chat.id, config.IG_STICKER)
        start_time = time.perf_counter()
        
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)
                
                # yt-dlp options for Instagram
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
                
                # Use Instagram cookies if available
                cookie_file = get_random_cookie(".")  # Look for cookies_instagram.txt
                if cookie_file and "instagram" in cookie_file.lower():
                    opts["cookiefile"] = cookie_file
                    logger.info(f"INSTAGRAM: Using cookie file")
                
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
                
                # Send video(s)
                for video_file in video_files:
                    await bot.send_video(
                        m.chat.id,
                        FSInputFile(video_file),
                        caption=format_download_complete(m.from_user, elapsed, "Instagram"),
                        parse_mode="HTML"
                    )
                
                logger.info(f"INSTAGRAM: Sent {len(video_files)} file(s) in {elapsed:.2f}s")
        
        except Exception as e:
            logger.error(f"INSTAGRAM ERROR: {e}")
            try:
                await bot.delete_message(m.chat.id, sticker.message_id)
            except:
                pass
            await m.answer(f"Instagram download failed\n{str(e)[:100]}")
