import asyncio
import logging
import os
import re
import glob
import secrets
import subprocess
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError
from aiogram.filters import BaseFilter
from aiogram.types import (
    Message,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from yt_dlp import YoutubeDL

# ================= CONFIG =================
BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

MAX_DURATION = 30 * 60        # 30 minutes
SEGMENT_TIME = 300            # 5 minutes
AUDIO_BITRATE = "128k"

QUALITY_PRESETS = {
    "1080p": "2.0M",
    "720p": "1.2M",
    "480p": "0.8M",
}

DEFAULT_QUALITY = "720p"
SELECTION_TIMEOUT = 15

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
    with YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("duration")

# ================= DOWNLOAD =================
def download_video(url: str) -> str | None:
    prefix = random_prefix()
    with YoutubeDL({
        "outtmpl": f"{prefix}.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "format": "bestvideo+bestaudio/best",
    }) as ydl:
        ydl.download([url])
    return find_file(prefix)

# ================= SEGMENT (QUALITY FIXED) =================
def segment_video(input_path: str, video_bitrate: str) -> list[str]:
    base = input_path.replace(".mp4", "")
    out_pattern = f"{base}_part%03d.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,

        # Aspect safe
        "-vf",
        "scale=iw*min(1280/iw\\,720/ih):ih*min(1280/iw\\,720/ih),"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2",

        # Frame stability
        "-r", "30",
        "-g", "60",
        "-keyint_min", "60",
        "-sc_threshold", "0",

        # Quality
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "23",
        "-maxrate", video_bitrate,
        "-bufsize", "2.5M",

        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,

        # Preview + segments
        "-movflags", "+faststart",
        "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_TIME})",

        "-f", "segment",
        "-segment_time", str(SEGMENT_TIME),
        "-reset_timestamps", "1",
        out_pattern
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sorted(glob.glob(f"{base}_part*.mp4"))

# ================= STATE =================
pending_quality: dict[int, tuple[str, int]] = {}

# ================= HANDLERS =================
@dp.message(HasURL())
async def handle_link(message: Message):
    chat_id = message.chat.id
    chat_type = message.chat.type
    urls = re.findall(r"https?://[^\s]+", message.text or "")

    for url in urls:

        # 🔞 XHAMSTER (PRIVATE)
        if is_private(url) and chat_type == "private":
            status = await bot.send_message(chat_id, "🔍 Checking video…")

            duration = get_duration(url)
            if not duration or duration > MAX_DURATION:
                await bot.edit_message_text(
                    text="❌ Video too long. Max allowed duration is 30 minutes.",
                    chat_id=chat_id,
                    message_id=status.message_id
                )
                return

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="1080p", callback_data="q_1080p"),
                    InlineKeyboardButton(text="720p", callback_data="q_720p"),
                    InlineKeyboardButton(text="480p", callback_data="q_480p"),
                ]]
            )

            await bot.edit_message_text(
                text="🎛️ Select video quality:",
                chat_id=chat_id,
                message_id=status.message_id,
                reply_markup=keyboard
            )

            pending_quality[chat_id] = (url, status.message_id)

            await asyncio.sleep(SELECTION_TIMEOUT)

            if chat_id in pending_quality:
                pending_quality.pop(chat_id)
                await process_video(chat_id, url, DEFAULT_QUALITY, status.message_id)

        # 🌍 PUBLIC LINKS
        elif is_public(url):
            try:
                await message.delete()
            except:
                pass

            status = await bot.send_message(chat_id, "⬇️ Downloading…")
            path = download_video(url)

            if not path:
                await bot.delete_message(chat_id, status.message_id)
                return

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
            os.unlink(path)

# ================= CALLBACK =================
@dp.callback_query(F.data.startswith("q_"))
async def on_quality(call: CallbackQuery):
    chat_id = call.message.chat.id
    quality = call.data.replace("q_", "")

    if chat_id not in pending_quality:
        await call.answer("Expired.", show_alert=True)
        return

    url, msg_id = pending_quality.pop(chat_id)
    await call.answer()
    await process_video(chat_id, url, quality, msg_id)

# ================= PROCESS =================
async def process_video(chat_id: int, url: str, quality: str, status_id: int):
    await bot.edit_message_text(
        text=f"⬇️ Downloading ({quality})…",
        chat_id=chat_id,
        message_id=status_id
    )

    path = download_video(url)
    if not path:
        return

    await bot.edit_message_text(
        text="✂️ Processing…",
        chat_id=chat_id,
        message_id=status_id
    )

    parts = segment_video(path, QUALITY_PRESETS[quality])
    await bot.delete_message(chat_id, status_id)

    sent_ids = []
    total = len(parts)

    for i, part in enumerate(parts, start=1):
        msg = await bot.send_video(
            chat_id=chat_id,
            video=FSInputFile(part),
            caption=f"Part {i}/{total} ({quality})"
        )
        sent_ids.append(msg.message_id)

    warn = await bot.send_message(
        chat_id,
        "⚠️ This video will be deleted in 30 seconds."
    )

    await asyncio.sleep(30)

    for mid in sent_ids:
        try:
            await bot.delete_message(chat_id, mid)
        except:
            pass

    try:
        await bot.delete_message(chat_id, warn.message_id)
    except:
        pass

    await bot.send_message(chat_id, "🧹 Your history was cleared.")

    for p in parts:
        os.unlink(p)
    os.unlink(path)

# ================= MAIN =================
async def main():
    me = await bot.get_me()
    logger.info(f"Bot started as @{me.username}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
