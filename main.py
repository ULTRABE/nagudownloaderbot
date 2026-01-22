import asyncio
import logging
import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse

import aiofiles
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError
from aiogram.filters import BaseFilter
from aiogram.types import Message
from yt_dlp import YoutubeDL

# Hardcoded bot token - replace with your token
BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

# Configure logging
logging.getLogger('aiogram.event').setLevel(logging.WARNING)
logging.getLogger('aiogram.dispatcher').setLevel(logging.WARNING)
logging.basicConfig(level=logging.WARNING)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

class HasVideoURL(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        text = message.text or message.caption or ""
        urls = re.findall(r'https?://[^\s]+', text)
        for url in urls:
            if await is_supported_url(url):
                return True
        return False

async def is_supported_url(url: str) -> bool:
    supported_domains = [
        'youtube.com', 'youtu.be', 'm.youtube.com', 'youtube-nocookie.com',
        'instagram.com', 'www.instagram.com',
        'facebook.com', 'm.facebook.com', 'fb.watch',
        'twitter.com', 'x.com', 'mobile.twitter.com',
        'pinterest.com', 'www.pinterest.com'
    ]
    domain = urlparse(url).netloc.lower()
    return any(s in domain for s in supported_domains)

async def get_video_info(url: str):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'get_duration': True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return info.get('duration', 0), info
        except:
            return 0, None

async def is_short_video(url: str, duration: int) -> bool:
    if duration and duration <= 60:
        return True
    
    short_patterns = [
        r'instagram\.com/reel/',
        r'facebook\.com/.*shorts',
        r'pinterest\.com/.*short'
    ]
    
    for pattern in short_patterns:
        if re.search(pattern, url.lower()):
            return True
    
    return False

async def download_video(url: str, status_message_id: int, chat_id: int):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"video_{timestamp}.mp4"
    
    try:
        duration, info = await get_video_info(url)
        is_short = await is_short_video(url, duration)
        
        if is_short:
            # Shorts/Reels: best mp4 up to 720p, target <=6MB
            format_selector = (
                'best[ext=mp4][height<=720]/'
                'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            )
        else:
            # Long videos: best 720p mp4
            format_selector = (
                'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/'
                'best[ext=mp4][height<=720]/best'
            )
        
        ydl_opts = {
            'format': format_selector,
            'outtmpl': filename,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'merge_output_format': 'mp4',
        }
        
        if is_short:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }]
        
        await bot.edit_message_text(
            "⬆️ Uploading...",
            chat_id,
            status_message_id
        )
        
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            return filename
        return None
        
    except Exception:
        return None

@dp.message(HasVideoURL())
async def handle_video_url(message: Message):
    chat_id = message.chat.id
    urls = re.findall(r'https?://[^\s]+', message.text or message.caption or "")
    
    for url in urls:
        if not await is_supported_url(url):
            continue
            
        try:
            # Step 1: Delete user message (best effort)
            try:
                await message.delete()
            except:
                pass
            
            # Step 2: Send status message
            status_msg = await bot.send_message(chat_id, "⬇️ Downloading...")
            
            # Step 3: Download
            video_path = await download_video(url, status_msg.message_id, chat_id)
            
            if not video_path:
                await bot.delete_message(chat_id, status_msg.message_id)
                continue
            
            try:
                # Step 4: Send video
                with open(video_path, 'rb') as video_file:
                    sent_msg = await bot.send_video(
                        chat_id=chat_id,
                        video=video_file,
                        caption="@nagudownloaderbot 🤍",
                        supports_streaming=True,
                        width=None,
                        height=None
                    )
                
                # Step 5: Pin video in groups (best effort)
                if message.chat.type != 'private':
                    try:
                        await bot.pin_chat_message(chat_id, sent_msg.message_id)
                    except TelegramForbiddenError:
                        pass
                
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.timeout)
                continue
            except Exception:
                pass
            finally:
                # Step 6: Delete status
                try:
                    await bot.delete_message(chat_id, status_msg.message_id)
                except:
                    pass
                
                # Step 7: Cleanup
                try:
                    os.unlink(video_path)
                except:
                    pass
                
        except Exception:
            try:
                await bot.delete_message(chat_id, status_msg.message_id)
            except:
                pass
            continue

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
