import asyncio
import logging
import os
import re
import glob
import secrets
import subprocess
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

MAX_DOCUMENT_SIZE = 2 * 1024 * 1024 * 1024  # 2GB Telegram bot limit

# =========================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ================= DOMAINS =================
PUBLIC_DOMAINS = [
    "instagram.com",
    "facebook.com",
    "fb.watch",
    "x.com",
    "twitter.com",
]

PRIVATE_DOC_DOMAINS = [
    "pornhub.org",
    "xhamster.com",
    "xhamster.xxx",
    "xhamster44.desi",
]

def domain(url: str) -> str:
    return urlparse(url).netloc.lower()

def is_public(url: str) -> bool:
    return any(d in domain(url) for d in PUBLIC_DOMAINS)

def is_private_doc(url: str) -> bool:
    return any(d in domain(url) for d in PRIVATE_DOC_DOMAINS)

# ================= FILTER =================
class HasURL(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(re.search(r"https?://", message.text or ""))

# ================= HELPERS =================
def random_filename():
    return f"file_{secrets.token_hex(8)}"

def find_file(prefix: str):
    files = glob.glob(f"{prefix}.*")
    return files[0] if files else None

def compress_video(input_path: str) -> str | None:
    """
    NORMALIZATION COMPRESSION:
    - Keeps quality reasonable
    - Reduces bitrate spikes
    - NOT trying to force small size
    """
    output_path = input_path.replace(".mp4", "_c.mp4")

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "24",              # balanced CRF
        "-maxrate", "2M",          # cap spikes
        "-bufsize", "4M",
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-level", "4.1",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(output_path):
            return output_path
    except Exception as e:
        logger.error(f"Compression failed: {e}")

    return None

# ================= DOWNLOAD =================
async def download_video(url: str):
    prefix = random_filename()

    ydl_opts = {
        "outtmpl": f"{prefix}.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "format": "bestvideo+bestaudio/best",
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        path = find_file(prefix)
        if not path or os.path.getsize(path) == 0:
            return None

        return path

    except Exception as e:
        logger.error(f"Download failed: {e}")
        return None

# ================= HANDLER =================
@dp.message(HasURL())
async def handler(message: Message):
    chat_id = message.chat.id
    chat_type = message.chat.type
    urls = re.findall(r"https?://[^\s]+", message.text or "")

    for url in urls:

        # 🔞 PRIVATE DOMAINS (XHAMSTER / PORNHUB)
        if is_private_doc(url):
            if chat_type != "private":
                continue

            status = await bot.send_message(chat_id, "⬇️ Downloading…")
            path = await download_video(url)

            if not path:
                await bot.delete_message(chat_id, status.message_id)
                continue

            # Normalize video to avoid bitrate spikes
            compressed = compress_video(path)
            if compressed:
                os.unlink(path)
                path = compressed

            file_size = os.path.getsize(path)

            if file_size > MAX_DOCUMENT_SIZE:
                await bot.edit_message_text(
                    "❌ File exceeds Telegram upload limit.",
                    chat_id,
                    status.message_id
                )
                os.unlink(path)
                continue

            await bot.delete_message(chat_id, status.message_id)

            sent = await bot.send_document(
                chat_id,
                FSInputFile(path),
                caption="⚠️ This file will be deleted in 30 seconds."
            )

            await asyncio.sleep(30)
            try:
                await bot.delete_message(chat_id, sent.message_id)
            except:
                pass

            os.unlink(path)
            continue

        # 🌍 PUBLIC DOMAINS (INSTAGRAM / FB) — UNCHANGED
        if not is_public(url):
            continue

        try:
            try:
                await message.delete()
            except:
                pass

            status = await bot.send_message(chat_id, "⬇️ Downloading…")
            path = await download_video(url)

            if not path:
                await bot.delete_message(chat_id, status.message_id)
                continue

            sent = await bot.send_video(
                chat_id,
                FSInputFile(path),
                caption="@nagudownloaderbot 🤍",
                supports_streaming=True
            )

            if chat_type != "private":
                try:
                    await bot.pin_chat_message(chat_id, sent.message_id)
                except TelegramForbiddenError:
                    pass

            await bot.delete_message(chat_id, status.message_id)

        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)

        finally:
            if path and os.path.exists(path):
                os.unlink(path)

# ================= MAIN =================
async def main():
    me = await bot.get_me()
    logger.info(f"Bot started as @{me.username}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
