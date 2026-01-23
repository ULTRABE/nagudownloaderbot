# =========================
# main.py — FINAL STABLE BUILD
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
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatType
from yt_dlp import YoutubeDL

# ================= CONFIG =================
BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"
OWNER_ID = 7363967303

CRF_NORMAL = "24"
CRF_ADULT = "26"
MAXRATE_ADULT = "1200k"

SOFT_LIMIT_NORMAL = 10 * 60
MAX_LIMIT_ADULT = 30 * 60

CHUNK_MB = 45
DELETE_ADULT_AFTER = 10

ADULT_GC_LINK = "https://t.me/+VUujjb34k9s2YTU1"

ADULT_KEYWORDS = [
    "porn", "xxx", "xhamster", "pornhub", "xnxx", "xvideos",
    "redtube", "youporn", "spankbang", "eporner", "beeg",
    "thisvid", "motherless", "hanime", "hentai"
]

AUTHORIZED_ADULT_CHATS = set()

# =========================================
logging.basicConfig(level=logging.WARNING)
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ================= FILTER =================
class HasURL(BaseFilter):
    async def __call__(self, m: Message):
        return bool(re.search(r"https?://", m.text or ""))

# ================= HELPERS =================
def domain(url: str) -> str:
    return urlparse(url).netloc.lower()

def is_adult(url: str, info: dict) -> bool:
    d = domain(url)
    return any(k in d for k in ADULT_KEYWORDS) or info.get("age_limit", 0) >= 18

def ytdlp_info(url):
    with YoutubeDL({
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 10
    }) as ydl:
        return ydl.extract_info(url, download=False)

def ytdlp_download(url, out):
    with YoutubeDL({
        "outtmpl": out,
        "merge_output_format": "mp4",
        "format": "bestvideo+bestaudio/best",
        "quiet": True,
        "noplaylist": True
    }) as ydl:
        ydl.download([url])

def reencode_adult(src, out):
    subprocess.run([
        "ffmpeg", "-y", "-i", src,
        "-vf", "scale=-2:540",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", CRF_ADULT,
        "-maxrate", MAXRATE_ADULT,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "96k",
        out
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def chunk_file(path):
    chunks = []
    size = CHUNK_MB * 1024 * 1024
    with open(path, "rb") as f:
        i = 0
        while True:
            data = f.read(size)
            if not data:
                break
            name = f"{path}.part{i}"
            with open(name, "wb") as c:
                c.write(data)
            chunks.append(name)
            i += 1
    return chunks

# ================= AUTH =================
@dp.message(Command("auth"))
async def auth(m: Message):
    if m.from_user.id == OWNER_ID:
        AUTHORIZED_ADULT_CHATS.add(m.chat.id)
        await m.reply("Adult downloads enabled here.")

@dp.message(Command("unauth"))
async def unauth(m: Message):
    if m.from_user.id == OWNER_ID:
        AUTHORIZED_ADULT_CHATS.discard(m.chat.id)
        await m.reply("Adult downloads disabled here.")

# ================= HANDLER =================
@dp.message(HasURL())
async def handler(m: Message):
    url = re.findall(r"https?://[^\s]+", m.text or "")[0]

    try:
        await m.delete()
    except:
        pass

    try:
        info = ytdlp_info(url)
    except:
        await bot.send_message(m.chat.id, "Unsupported link.")
        return

    if info.get("is_live") or info.get("_type") == "playlist":
        await bot.send_message(m.chat.id, "Unsupported link.")
        return

    adult = is_adult(url, info)

    # ================= NORMAL =================
    if not adult:
        if (info.get("duration") or 0) > SOFT_LIMIT_NORMAL:
            await bot.send_message(m.chat.id, "Video too long.")
            return

        status = await bot.send_message(m.chat.id, "Downloading…")
        base = f"n_{secrets.token_hex(6)}"
        raw = f"{base}.mp4"

        ytdlp_download(url, raw)
        await status.edit_text("Uploading…")

        sent = await bot.send_video(
            m.chat.id,
            FSInputFile(raw),
            caption="@nagudownloaderbot 🤍",
            supports_streaming=True
        )

        if m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            try:
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            except:
                pass

        os.remove(raw)
        await status.delete()
        return

    # ================= ADULT =================
    if m.chat.id not in AUTHORIZED_ADULT_CHATS:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("Join private group", url=ADULT_GC_LINK)]
        ])
        await bot.send_message(m.chat.id, "18+ content not allowed here.", reply_markup=kb)
        return

    if (info.get("duration") or 0) > MAX_LIMIT_ADULT:
        await bot.send_message(m.chat.id, "18+ video too long.")
        return

    status = await bot.send_message(m.chat.id, "Downloading…")
    base = f"a_{secrets.token_hex(6)}"
    raw = f"{base}_raw.mp4"
    final = f"{base}.mp4"

    ytdlp_download(url, raw)
    await status.edit_text("Processing…")
    reencode_adult(raw, final)
    await status.edit_text("Uploading…")

    try:
        await bot.send_video(m.chat.id, FSInputFile(final), supports_streaming=True)
    except:
        for part in chunk_file(final):
            await bot.send_document(m.chat.id, FSInputFile(part))
            os.remove(part)

    warn = await bot.send_message(m.chat.id, "This media will be deleted in 10 seconds.")
    await asyncio.sleep(DELETE_ADULT_AFTER)

    for msg in (warn, status):
        try:
            await msg.delete()
        except:
            pass

    os.remove(raw)
    os.remove(final)
    await bot.send_message(m.chat.id, "History cleared.")

# ================= MAIN =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
