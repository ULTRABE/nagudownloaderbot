# =========================
# main.py — FINAL STABLE BUILD (CHUNK + FALLBACK FIX)
# =========================

import asyncio
import logging
import os
import re
import secrets
import subprocess
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher
from aiogram.filters import BaseFilter, Command
from aiogram.types import (
    Message,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ChatType
from yt_dlp import YoutubeDL

# ================= CONFIG =================
BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"
OWNER_ID = 7363967303

CRF_NORMAL = "24"
CRF_ADULT = "23"
MAXRATE = "4M"
BUFSIZE = "8M"

SOFT_LIMIT_NORMAL = 10 * 60
MAX_LIMIT_ADULT = 30 * 60

CHUNK_MB = 45
DELETE_ADULT_AFTER = 10

ADULT_GC_LINK = "https://t.me/+5BX6H7j4osVjOWZl"

ADULT_KEYWORDS = [
    "porn", "sex", "xxx",
    "pornhub", "xhamster", "xnxx", "xvideos",
    "redtube", "youporn", "spankbang", "tube8",
    "eporner", "beeg", "thisvid", "motherless",
    "hentai", "hanime", "ecchi"
]

AUTHORIZED_ADULT_CHATS = set()

# =========================================
logging.basicConfig(level=logging.WARNING)
bot = Bot(BOT_TOKEN, parse_mode=None)
dp = Dispatcher()

# ================= FILTER =================
class HasURL(BaseFilter):
    async def __call__(self, m: Message):
        return bool(re.search(r"https?://", m.text or ""))

# ================= HELPERS =================
def domain(url: str) -> str:
    return urlparse(url).netloc.lower()

def is_adult(url: str, info: dict | None) -> bool:
    d = domain(url)
    if any(k in d for k in ADULT_KEYWORDS):
        return True
    if info and info.get("age_limit", 0) >= 18:
        return True
    return False

def extract_info_safe(url):
    try:
        with YoutubeDL({
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 10,
        }) as ydl:
            return ydl.extract_info(url, download=False)
    except:
        return None

def download(url, out):
    with YoutubeDL({
        "outtmpl": out,
        "merge_output_format": "mp4",
        "format": "bestvideo+bestaudio/best",
        "quiet": True,
        "noplaylist": True,
    }) as ydl:
        ydl.download([url])

def split_video(path):
    parts = []
    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb <= CHUNK_MB:
        return [path]

    base = path.replace(".mp4", "")
    cmd = [
        "ffmpeg", "-y", "-i", path,
        "-c", "copy",
        "-map", "0",
        "-f", "segment",
        "-segment_size", str(CHUNK_MB * 1024 * 1024),
        f"{base}_part_%03d.mp4"
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for f in sorted(os.listdir(".")):
        if f.startswith(os.path.basename(base)) and f.endswith(".mp4"):
            parts.append(f)
    os.remove(path)
    return parts

# ================= AUTH =================
@dp.message(Command("auth"))
async def auth(m: Message):
    if m.from_user.id == OWNER_ID:
        AUTHORIZED_ADULT_CHATS.add(m.chat.id)
        await m.reply("Adult downloads enabled in this chat.")

@dp.message(Command("unauth"))
async def unauth(m: Message):
    if m.from_user.id == OWNER_ID:
        AUTHORIZED_ADULT_CHATS.discard(m.chat.id)
        await m.reply("Adult downloads disabled in this chat.")

# ================= HANDLER =================
@dp.message(HasURL())
async def handler(m: Message):
    url = re.findall(r"https?://[^\s]+", m.text or "")[0]

    # 🔥 Immediate deletion
    try:
        await m.delete()
    except:
        pass

    info = extract_info_safe(url)
    adult = is_adult(url, info)

    # 🔴 Block adult in unauthorized GCs
    if adult and m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and m.chat.id not in AUTHORIZED_ADULT_CHATS:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="Join private group for 18+ content",
                url=ADULT_GC_LINK
            )
        ]])
        await bot.send_message(m.chat.id, "Unsupported link.", reply_markup=kb)
        return

    # ========= NORMAL =========
    if not adult:
        if info and (info.get("duration") or 0) > SOFT_LIMIT_NORMAL:
            await bot.send_message(m.chat.id, "Video is too long.")
            return

        status = await bot.send_message(m.chat.id, "Downloading…")

        base = f"n_{secrets.token_hex(6)}"
        raw = f"{base}_raw.mp4"
        out = f"{base}.mp4"

        try:
            download(url, raw)
        except:
            await status.edit_text("Unsupported link.")
            return

        await status.edit_text("Uploading…")

        subprocess.run([
            "ffmpeg", "-y", "-i", raw,
            "-c:v", "libx264", "-preset", "veryfast",
            "-crf", CRF_NORMAL,
            "-maxrate", MAXRATE, "-bufsize", BUFSIZE,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "128k",
            out
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        sent = await bot.send_video(
            m.chat.id,
            FSInputFile(out),
            caption="@nagudownloaderbot 🤍",
            supports_streaming=True
        )

        if m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            try:
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            except:
                pass

        os.remove(raw)
        os.remove(out)
        await status.delete()
        return

    # ========= ADULT =========
    if info and (info.get("duration") or 0) > MAX_LIMIT_ADULT:
        await bot.send_message(m.chat.id, "18+ video is too long.")
        return

    status = await bot.send_message(m.chat.id, "Downloading…")
    base = f"a_{secrets.token_hex(6)}"
    raw = f"{base}.mp4"

    try:
        download(url, raw)
    except:
        await status.edit_text("Unsupported link.")
        return

    await status.edit_text("Uploading…")

    parts = split_video(raw)
    sent_msgs = []

    for p in parts:
        sent = await bot.send_video(
            m.chat.id,
            FSInputFile(p),
            supports_streaming=True
        )
        sent_msgs.append(sent)
        os.remove(p)

    warn = await bot.send_message(
        m.chat.id,
        "This media will be deleted in 10 seconds. Save it now."
    )

    await asyncio.sleep(DELETE_ADULT_AFTER)

    for msg in sent_msgs + [warn]:
        try:
            await bot.delete_message(m.chat.id, msg.message_id)
        except:
            pass

    await bot.send_message(m.chat.id, "History cleared.")
    await status.delete()

# ================= MAIN =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
