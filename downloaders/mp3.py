"""MP3 downloader - fully async with proper audio sending"""
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
from ui.formatting import format_audio_caption
from utils.helpers import get_random_cookie
from utils.logger import logger

async def handle_mp3_search(m: Message, query: str):
    """Search and download single song with proper metadata and thumbnail"""
    async with music_semaphore:
        logger.info(f"MP3: {query}")
        sticker = await bot.send_sticker(m.chat.id, config.MUSIC_STICKER)
        start = time.perf_counter()

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)
                
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
                        "DNT": "1",
                    },
                    "default_search": "ytsearch1",
                    "writethumbnail": True,
                    "socket_timeout": 30,
                    "retries": 3,
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        },
                        {
                            "key": "EmbedThumbnail",
                            "already_have_thumbnail": False,
                        },
                        {
                            "key": "FFmpegMetadata",
                            "add_metadata": True,
                        }
                    ],
                    "postprocessor_args": [
                        "-ar", "44100",
                        "-ac", "2",
                        "-b:a", "192k",
                    ],
                }
                
                # Use random cookie from yt_music_cookies folder
                cookie_file = get_random_cookie(config.YT_MUSIC_COOKIES_FOLDER)
                if cookie_file:
                    opts["cookiefile"] = cookie_file
                    logger.info(f"MP3: Using cookie {cookie_file}")
                
                # Search and download
                with YoutubeDL(opts) as ydl:
                    info = await asyncio.to_thread(
                        lambda: ydl.extract_info(f"ytsearch1:{query}", download=True)
                    )
                
                # Find MP3
                mp3 = None
                for f in tmp.iterdir():
                    if f.suffix == ".mp3":
                        mp3 = f
                        break
                
                if not mp3:
                    await bot.delete_message(m.chat.id, sticker.message_id)
                    await m.answer("❌ 𝐒𝐨𝐧𝐠 𝐧𝐨𝐭 𝐟𝐨𝐮𝐧𝐝")
                    return
                
                # Extract metadata
                entry = info['entries'][0] if 'entries' in info else info
                title = entry.get('title', mp3.stem)
                artist = entry.get('artist') or entry.get('uploader', 'Unknown Artist')
                file_size = mp3.stat().st_size / 1024 / 1024
                
                elapsed = time.perf_counter() - start
                await bot.delete_message(m.chat.id, sticker.message_id)
                
                # Send to chat with proper audio metadata
                await bot.send_audio(
                    m.chat.id,
                    FSInputFile(mp3),
                    caption=format_audio_caption(m.from_user, elapsed, title, artist, file_size),
                    parse_mode="HTML",
                    title=title,
                    performer=artist
                )
                
                logger.info(f"MP3: {title} by {artist} ({file_size:.1f}MB) in {elapsed:.2f}s")
                
        except Exception as e:
            logger.error(f"MP3: {e}")
            try:
                await bot.delete_message(m.chat.id, sticker.message_id)
            except:
                pass
            await m.answer(f"❌ 𝐌𝐏𝟑 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}")

@dp.message(Command("mp3"))
async def mp3_command(m: Message):
    """MP3 command handler"""
    query = m.text.replace("/mp3", "").strip()
    if not query:
        await m.answer("𝐔𝐬𝐚𝐠𝐞: /mp3 song name")
        return
    await handle_mp3_search(m, query)
