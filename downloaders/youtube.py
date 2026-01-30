"""YouTube downloader - fully async with cookie rotation"""
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
from utils.helpers import get_random_cookie
from utils.logger import logger

async def handle_youtube(m: Message, url: str):
    """Handle YouTube download request"""
    async with download_semaphore:
        logger.info(f"YT: {url}")
        sticker = await bot.send_sticker(m.chat.id, config.YT_STICKER)
        start = time.perf_counter()

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)
                raw = tmp / "yt.mp4"
                final = tmp / "ytf.mp4"

                opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "format": "best[height<=720][ext=mp4]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best",
                    "merge_output_format": "mp4",
                    "outtmpl": str(raw),
                    "proxy": config.pick_proxy(),
                    "http_headers": {
                        "User-Agent": config.pick_user_agent(),
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "DNT": "1",
                    },
                    "socket_timeout": 30,
                    "retries": 3,
                    "concurrent_fragment_downloads": 20,
                    "extractor_args": {
                        "youtube": {
                            "player_client": ["android", "web"],
                            "player_skip": ["webpage", "configs"],
                        }
                    },
                }
                
                # Try without cookies first, then with rotation
                try:
                    await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))
                except:
                    cookie_file = get_random_cookie(config.YT_COOKIES_FOLDER)
                    if cookie_file:
                        logger.info(f"YT: Using cookie {cookie_file}")
                        opts["cookiefile"] = cookie_file
                        await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))
                    else:
                        raise

                # VP9 with bitrate (up to 12MB)
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", str(raw),
                    "-vf", "scale=720:-2",
                    "-c:v", "libvpx-vp9", "-b:v", "1200k", "-maxrate", "1500k", "-bufsize", "2400k",
                    "-cpu-used", "4", "-row-mt", "1",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "libopus", "-b:a", "128k",
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
                
                logger.info(f"YT: Done in {elapsed:.2f}s")
                
        except Exception as e:
            logger.error(f"YT: {e}")
            try:
                await bot.delete_message(m.chat.id, sticker.message_id)
            except:
                pass
            await m.answer(f"❌ 𝐘𝐨𝐮𝐓𝐮𝐛𝐞 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}")
