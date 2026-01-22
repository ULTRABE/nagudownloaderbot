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
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

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
        'youtube.com', 'youtu.be',
        'instagram.com', 'facebook.com',
        'twitter.com', 'x.com',
        'pinterest.com'
    ]
    domain = urlparse(url).netloc.lower()
    return any(s in domain for s in supported_domains)

async def get_video_info(url: str):
    with YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return info.get('duration', 0), info
        except Exception as e:
            logger.error(f"extract_info failed: {e}")
            return 0, None

def find_downloaded_file(timestamp: str):
    matches = glob.glob(f"video_{timestamp}.*")
    return matches[0] if matches else None

async def download_video(url: str, status_message_id: int, chat_id: int):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    try:
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
            'merge_output_format': 'mp4',
            'noplaylist': True
        }

        logger.info(f"Starting download for {url}")
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        video_path = find_downloaded_file(timestamp)
        if not video_path:
            return None

        await bot.edit_message_text(
            text="⬆️ Uploading...",
            chat_id=chat_id,
            message_id=status_message_id
        )

        return video_path

    except Exception as e:
        logger.error(f"Download failed: {e}")
        return None

@dp.message(HasVideoURL())
async def handle_video_url(message: Message):
    chat_id = message.chat.id
    urls = re.findall(r'https?://[^\s]+', message.text or message.caption or "")

    for url in urls:
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
                continue

            video_file = FSInputFile(video_path)
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
                    pass

            await bot.delete_message(chat_id, status_msg.message_id)

        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        finally:
            if video_path and os.path.exists(video_path):
                os.unlink(video_path)

async def main():
    me = await bot.get_me()
    logger.info(f"Bot starting - @{me.username}")
    logger.info("Polling started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
