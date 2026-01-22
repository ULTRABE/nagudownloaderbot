import asyncio
import logging
import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse
import glob

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError
from aiogram.filters import BaseFilter
from aiogram.types import Message
from yt_dlp import YoutubeDL

# Replace with your bot token
BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger('aiogram.event').setLevel(logging.WARNING)

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
    }
    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            duration = info.get('duration', 0) if info else 0
            return duration, info
        except Exception as e:
            logger.error(f"Failed to extract info for {url}: {e}")
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

def find_downloaded_file(timestamp: str):
    patterns = [
        f"video_{timestamp}.*",
    ]
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    return None

async def download_video(url: str, status_message_id: int, chat_id: int):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    
    try:
        duration, info = await get_video_info(url)
        _ = await is_short_video(url, duration)
        
        format_selector = (
            'best[ext=mp4]/'
            'bestvideo[ext=mp4]+bestaudio[ext=m4a]/'
            'best'
        )
        
        ydl_opts = {
            'format': format_selector,
            'outtmpl': f'video_{timestamp}.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'merge_output_format': 'mp4',
        }
        
        logger.info(f"Starting download for {url}")
        
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        video_path = find_downloaded_file(timestamp)
        
        if not video_path or not os.path.exists(video_path):
            logger.error(f"No video file found for timestamp {timestamp}")
            return None
        
        logger.info(f"Download successful: {video_path}")
        
        # ✅ FIXED: aiogram v3 requires keyword arguments
        await bot.edit_message_text(
            text="⬆️ Uploading...",
            chat_id=chat_id,
            message_id=status_message_id
        )
        
        return video_path
        
    except Exception as e:
        logger.error(f"Download failed for {url}: {e}")
        return None

@dp.message(HasVideoURL())
async def handle_video_url(message: Message):
    chat_id = message.chat.id
    urls = re.findall(r'https?://[^\s]+', message.text or message.caption or "")
    
    for url in urls:
        if not await is_supported_url(url):
            continue
            
        status_msg = None
        video_path = None
        try:
            try:
                await message.delete()
            except:
                pass
            
            status_msg = await bot.send_message(chat_id, "⬇️ Downloading...")
            
            video_path = await download_video(url, status_msg.message_id, chat_id)
            
            if not video_path:
                logger.warning(f"No video to send for {url}")
                continue
            
            with open(video_path, 'rb') as video_file:
                sent_msg = await bot.send_video(
                    chat_id=chat_id,
                    video=video_file,
                    caption="@nagudownloaderbot 🤍",
                    supports_streaming=True
                )
            
            if message.chat.type != 'private':
                try:
                    await bot.pin_chat_message(chat_id, sent_msg.message_id)
                except TelegramForbiddenError:
                    logger.warning("Could not pin message")
                except Exception as e:
                    logger.error(f"Pin error: {e}")
            
            # delete status only after successful send
            try:
                await bot.delete_message(chat_id, status_msg.message_id)
            except:
                pass
            
        except TelegramRetryAfter as e:
            logger.warning(f"Rate limited, waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            continue
        except Exception as e:
            logger.error(f"Handler error for {url}: {e}")
        finally:
            if video_path and os.path.exists(video_path):
                try:
                    os.unlink(video_path)
                except:
                    pass

async def main():
    me = await bot.get_me()
    logger.info(f"Bot starting - @{me.username}")
    logger.info("Polling started")
    
    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Bot stopped")

if __name__ == "__main__":
    asyncio.run(main())
