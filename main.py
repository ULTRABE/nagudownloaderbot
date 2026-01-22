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

# Adult video limits
MAX_DURATION = 30 * 60          # 30 minutes
SEGMENT_TIME = 300              # 5 minutes per segment
VIDEO_BITRATE = "1.2M"
AUDIO_BITRATE = "128k"

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

# 🔒 XHAMSTER ONLY
PRIVATE_DOMAINS = [
    "xhamster.com",
    "xhamster.xxx",
    "xhamster44.desi",
]

def domain(url: str) -> str:
    return urlparse(url).netloc.lower()

def is_public(url: str) -> bool:
    return any(d in domain(url) for d in PUBLIC_DOMAINS)

def is_private(url: str) -> bool:
    return any(d in domain(url) for d in PRIVATE_DOMAINS)

# ================= FILTER =================
class HasURL(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(re.search(r"https?://", message.text or ""))

# ================= HELPERS =================
def random_prefix():
    return f"vid_{secrets.token_hex(6)}"

def find_file(prefix: str):
    files = glob.glob(f"{prefix}.*")
    return files[0] if files else None

# ================= METADATA =================
def get_duration(url: str) -> int | None:
    ydl_opts = {"quiet": True, "skip_download": True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("duration")

# ================= DOWNLOAD =================
def download_video(url: str) -> str | None:
    prefix = random_prefix()
    ydl_opts = {
        "outtmpl": f"{prefix}.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "format": "bestvideo+bestaudio/best",
    }
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return find_file(prefix)

# ================= SEGMENT (PREVIEW SAFE) =================
def segment_video(input_path: str) -> list[str]:
    base = input_path.replace(".mp4", "")
    out_pattern = f"{base}_part%03d.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,

        # 🔑 PREVIEW FIX
        "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_TIME})",
        "-movflags", "+faststart",

        "-c:v", "libx264",
        "-b:v", VIDEO_BITRATE,
        "-maxrate", VIDEO_BITRATE,
        "-bufsize", "2.4M",
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-level", "4.1",
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,

        "-f", "segment",
        "-segment_time", str(SEGMENT_TIME),
        "-reset_timestamps", "1",
        out_pattern
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sorted(glob.glob(f"{base}_part*.mp4"))

# ================= HANDLER =================
@dp.message(HasURL())
async def handler(message: Message):
    chat_id = message.chat.id
    chat_type = message.chat.type
    urls = re.findall(r"https?://[^\s]+", message.text or "")

    for url in urls:

        # 🔞 XHAMSTER (PRIVATE ONLY)
        if is_private(url):
            if chat_type != "private":
                continue

            status = await bot.send_message(chat_id, "🔍 Checking video…")

            duration = get_duration(url)
            if not duration or duration > MAX_DURATION:
                await bot.edit_message_text(
                    text="❌ Video too long. Max allowed duration is 30 minutes.",
                    chat_id=chat_id,
                    message_id=status.message_id
                )
                continue

            await bot.edit_message_text(
                text="⬇️ Downloading…",
                chat_id=chat_id,
                message_id=status.message_id
            )

            path = download_video(url)
            if not path:
                await bot.delete_message(chat_id, status.message_id)
                continue

            await bot.edit_message_text(
                text="✂️ Processing…",
                chat_id=chat_id,
                message_id=status.message_id
            )

            parts = segment_video(path)
            await bot.delete_message(chat_id, status.message_id)

            sent_ids = []
            total = len(parts)

            for i, part in enumerate(parts, start=1):
                msg = await bot.send_video(
                    chat_id=chat_id,
                    video=FSInputFile(part),
                    caption=f"Part {i}/{total}"
                )
                sent_ids.append(msg.message_id)

            # ⚠️ Temporary warning
            warning = await bot.send_message(
                chat_id,
                "⚠️ This video will be deleted in 30 seconds."
            )

            await asyncio.sleep(30)

            # Delete videos + warning
            for mid in sent_ids:
                try:
                    await bot.delete_message(chat_id, mid)
                except:
                    pass

            try:
                await bot.delete_message(chat_id, warning.message_id)
            except:
                pass

            # 🧹 Permanent confirmation
            await bot.send_message(
                chat_id,
                "🧹 Your history was cleared."
            )

            for p in parts:
                os.unlink(p)
            os.unlink(path)
            continue

        # 🌍 PUBLIC SITES (ORIGINAL BEHAVIOR)
        if not is_public(url):
            continue

        try:
            try:
                await message.delete()
            except:
                pass

            status = await bot.send_message(chat_id, "⬇️ Downloading…")
            path = download_video(url)

            if not path:
                await bot.delete_message(chat_id, status.message_id)
                continue

            sent = await bot.send_video(
                chat_id=chat_id,
                video=FSInputFile(path),
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
