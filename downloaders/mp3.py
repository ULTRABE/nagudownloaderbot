"""MP3 downloader - Fully async with proper audio metadata"""
import asyncio
import time
import tempfile
from pathlib import Path
from yt_dlp import YoutubeDL
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command

from core.bot import bot, dp
from core.config import config
from workers.task_queue import music_semaphore
from ui.formatting import format_audio_info
from utils.helpers import get_random_cookie, get_file_size_mb
from utils.logger import logger

async def handle_mp3_search(m: Message, query: str):
    """
    Search and download single song with metadata and thumbnail
    Fully async, non-blocking implementation
    """
    async with music_semaphore:
        logger.info(f"MP3: Searching for '{query}'")
        
        # Send progress message
        progress_msg = await m.answer(f"🔍 Searching for: {query}...")
        start_time = time.perf_counter()
        
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)
                
                # yt-dlp options for best audio quality
                opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "format": "bestaudio/best",
                    "outtmpl": str(tmp / "%(title)s.%(ext)s"),
                    "proxy": config.pick_proxy(),
                    "http_headers": {
                        "User-Agent": config.pick_user_agent(),
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "DNT": "1"
                    },
                    "default_search": "ytsearch1",
                    "writethumbnail": True,
                    "socket_timeout": 30,
                    "retries": 3,
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192"
                        },
                        {
                            "key": "EmbedThumbnail",
                            "already_have_thumbnail": False
                        },
                        {
                            "key": "FFmpegMetadata",
                            "add_metadata": True
                        }
                    ],
                    "postprocessor_args": [
                        "-ar", "44100",
                        "-ac", "2",
                        "-b:a", "192k"
                    ]
                }
                
                # Use random cookie from yt music cookies folder
                cookie_file = get_random_cookie(config.YT_MUSIC_COOKIES_FOLDER)
                if cookie_file:
                    opts["cookiefile"] = cookie_file
                    logger.info(f"MP3: Using cookie {Path(cookie_file).name}")
                
                # Search and download asynchronously
                with YoutubeDL(opts) as ydl:
                    info = await asyncio.to_thread(
                        lambda: ydl.extract_info(f"ytsearch1:{query}", download=True)
                    )
                
                # Find downloaded MP3 file
                mp3_file = None
                for f in tmp.iterdir():
                    if f.suffix == ".mp3":
                        mp3_file = f
                        break
                
                if not mp3_file:
                    await progress_msg.delete()
                    await m.answer("❌ Song not found")
                    return
                
                # Extract metadata
                entry = info['entries'][0] if 'entries' in info else info
                title = entry.get('title', mp3_file.stem)
                artist = entry.get('artist') or entry.get('uploader', 'Unknown Artist')
                file_size = get_file_size_mb(str(mp3_file))
                
                elapsed = time.perf_counter() - start_time
                
                # Delete progress message and user's command
                try:
                    await progress_msg.delete()
                    await m.delete()
                except:
                    pass
                
                # Send audio with metadata (this won't be deleted)
                await bot.send_audio(
                    m.chat.id,
                    FSInputFile(mp3_file),
                    caption=format_audio_info(m.from_user, title, artist, file_size, elapsed),
                    parse_mode="HTML",
                    title=title,
                    performer=artist
                )
                
                logger.info(f"MP3: Sent '{title}' by {artist} ({file_size:.1f}MB) in {elapsed:.2f}s")
        
        except Exception as e:
            logger.error(f"MP3 ERROR: {e}")
            try:
                await progress_msg.delete()
                await m.delete()
            except:
                pass
            await bot.send_message(m.chat.id, f"❌ MP3 download failed\n{str(e)[:100]}")

@dp.message(Command("mp3"))
async def mp3_command(m: Message):
    """MP3 command handler"""
    query = m.text.replace("/mp3", "").strip()
    
    if not query:
        await m.answer("Usage: /mp3 <song name>")
        return
    
    await handle_mp3_search(m, query)
