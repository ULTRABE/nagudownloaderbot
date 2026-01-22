import asyncio
import logging
import os
import re
import glob
from datetime import datetime
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError
from aiogram.filters import BaseFilter
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

# ================= CONFIG =================
BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"
OWNER_ID = 7363967303  # <-- your Telegram user ID
COOKIES_FILE = "cookies.txt"

# =========================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ================= FILTER =================
class HasVideoURL(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        text = message.text or message.caption or ""
        return bool(re.search(r"https?://", text))

# ================= HELPERS =================
def is_youtube(url: str) -> bool:
    return any(x in url for x in ["youtube.com", "youtu.be"])

def find_downloaded_file(ts: str):
    files = glob.glob(f"video_{ts}.*")
    return files[0] if files else None

async def notify_cookie_expired():
    try:
        await bot.send_message(
            OWNER_ID,
            "⚠️ <b>YouTube cookies are expired or invalid.</b>\n\n"
            "Please update <code>cookies.txt</code> in the GitHub repo and redeploy."
        )
    except:
        pass

# ================= DOWNLOAD =================
async def download_video(url: str, status_msg_id: int, chat_id: int):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    ydl_opts = {
        "outtmpl": f"video_{ts}.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "format": (
            "bv*[vcodec^=avc1][height<=1080]+ba[acodec^=mp4a]/"
            "b[vcodec^=avc1]/b"
        ),
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4"
        }],
        "postprocessor_args": [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart"
        ],
    }

    # Use cookies ONLY if YouTube
    if is_youtube(url):
        if os.path.exists(COOKIES_FILE):
            ydl_opts["cookiefile"] = COOKIES_FILE

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        video_path = find_downloaded_file(ts)
        if not video_path or os.path.getsize(video_path) == 0:
            raise Exception("Empty output file")

        await bot.edit_message_text(
            text="⬆️ Uploading...",
            chat_id=chat_id,
            message_id=status_msg_id
        )

        return video_path

    except Exception as e:
        err = str(e).lower()
        logger.error(f"Download failed: {e}")

        if is_youtube(url) and any(x in err for x in ["sign in", "cookie", "403", "empty"]):
            await notify_cookie_expired()

        return None

# ================= HANDLER =================
@dp.message(HasVideoURL())
async def handle_video(message: Message):
    chat_id = message.chat.id
    urls = re.findall(r"https?://[^\s]+", message.text or "")

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

            video = FSInputFile(video_path)
            sent = await bot.send_video(
                chat_id,
                video,
                caption="@nagudownloaderbot 🤍",
                supports_streaming=True
            )

            if message.chat.type != "private":
                try:
                    await bot.pin_chat_message(chat_id, sent.message_id)
                except TelegramForbiddenError:
                    pass

            await bot.delete_message(chat_id, status_msg.message_id)

        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)

        finally:
            if video_path and os.path.exists(video_path):
                os.unlink(video_path)

# ================= MAIN =================
async def main():
    me = await bot.get_me()
    logger.info(f"Bot started as @{me.username}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
