"""YouTube downloader - Fully async with cookie rotation"""
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

async def handle_youtube(m: Message, url: str):
    """
    Download YouTube videos, shorts, streams
    Uses rotating cookies for reliability
    """
    async with download_semaphore:
        logger.info(f"YOUTUBE: {url}")
        
        # Send sticker as progress indicator
        sticker = await bot.send_sticker(m.chat.id, config.YT_STICKER)
        start_time = time.perf_counter()
        
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)
                
                # yt-dlp options for YouTube
                opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "format": "best[height<=720]",  # Limit to 720p for faster downloads
                    "outtmpl": str(tmp / "%(title)s.%(ext)s"),
                    "proxy": config.pick_proxy(),
                    "http_headers": {
                        "User-Agent": config.pick_user_agent()
                    },
                    "socket_timeout": 30,
                    "retries": 3
                }
                
                # Use random cookie from yt cookies folder
                cookie_file = get_random_cookie(config.YT_COOKIES_FOLDER)
                if cookie_file:
                    opts["cookiefile"] = cookie_file
                    logger.info(f"YOUTUBE: Using cookie {Path(cookie_file).name}")
                
                # Download asynchronously
                with YoutubeDL(opts) as ydl:
                    await asyncio.to_thread(
                        lambda: ydl.download([url])
                    )
                
                # Find downloaded files
                video_files = list(tmp.glob("*.mp4")) + list(tmp.glob("*.webm")) + list(tmp.glob("*.mkv"))
                
                if not video_files:
                    await bot.delete_message(m.chat.id, sticker.message_id)
                    await m.answer("No video found")
                    return
                
                elapsed = time.perf_counter() - start_time
                
                # Delete sticker
                await bot.delete_message(m.chat.id, sticker.message_id)
                
                # Send video
                video_file = video_files[0]
                
                # Check file size (Telegram limit is 50MB for videos)
                file_size_mb = video_file.stat().st_size / 1024 / 1024
                
                if file_size_mb > 50:
                    # Send as document if too large
                    await bot.send_document(
                        m.chat.id,
                        FSInputFile(video_file),
                        caption=format_download_complete(m.from_user, elapsed, "YouTube"),
                        parse_mode="HTML"
                    )
                else:
                    await bot.send_video(
                        m.chat.id,
                        FSInputFile(video_file),
                        caption=format_download_complete(m.from_user, elapsed, "YouTube"),
                        parse_mode="HTML"
                    )
                
                logger.info(f"YOUTUBE: Sent video ({file_size_mb:.1f}MB) in {elapsed:.2f}s")
        
        except Exception as e:
            logger.error(f"YOUTUBE ERROR: {e}")
            try:
                await bot.delete_message(m.chat.id, sticker.message_id)
            except:
                pass
            await m.answer(f"YouTube download failed\n{str(e)[:100]}")
