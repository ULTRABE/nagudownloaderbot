# =========================
# main.py — STABLE FIXED BUILD
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
CRF_ADULT = "23"
MAXRATE = "4M"
BUFSIZE = "8M"

SOFT_LIMIT_NORMAL = 10 * 60
MAX_LIMIT_ADULT = 30 * 60

DELETE_ADULT_AFTER = 10
MAX_TG_MB = 190

ADULT_GC_LINK = "https://t.me/+VUujjb34k9s2YTU1"

ADULT_KEYWORDS = [
    "pornhub", "xhamster", "xnxx", "xvideos", "redtube",
    "youporn", "spankbang", "tube8", "eporner", "beeg",
    "thisvid", "motherless",
    "hentai", "hanime", "hentaihaven", "hentaistream",
    "hentaiworld", "hentaigasm", "hentaifox",
    "animeidhentai", "hentaiwebtoon", "hentaidude"
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
    if any(k in d for k in ADULT_KEYWORDS):
        return True
    if info.get("age_limit", 0) >= 18:
        return True
    return False

def extract_info(url):
    with YoutubeDL({
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
    }) as ydl:
        return ydl.extract_info(url, download=False)

def download(url, out):
    with YoutubeDL({
        "outtmpl": out,
        "merge_output_format": "mp4",
        "format": "bestvideo+bestaudio/best",
        "quiet": True,
        "noplaylist": True,
    }) as ydl:
        ydl.download([url])

def ffmpeg_recode(inp, out):
    subprocess.run([
        "ffmpeg", "-y", "-i", inp,
        "-c:v", "libx264", "-preset", "veryfast",
        "-crf", CRF_NORMAL,
        "-maxrate", MAXRATE, "-bufsize", BUFSIZE,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "128k",
        out
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ================= AUTH =================
@dp.message(Command("auth"))
async def auth(m: Message):
    if m.from_user.id == OWNER_ID:
        AUTHORIZED_ADULT_CHATS.add(m.chat.id)
        await m.answer("Adult downloads enabled.")

@dp.message(Command("unauth"))
async def unauth(m: Message):
    if m.from_user.id == OWNER_ID:
        AUTHORIZED_ADULT_CHATS.discard(m.chat.id)
        await m.answer("Adult downloads disabled.")

# ================= HANDLER =================
@dp.message(HasURL())
async def handler(m: Message):
    url = re.findall(r"https?://[^\s]+", m.text or "")[0]

    # 🔒 DELETE LINK IMMEDIATELY
    try:
        await m.delete()
    except:
        pass

    # Extract info safely
    try:
        info = extract_info(url)
    except:
        info = {}

    adult = is_adult(url, info)

    if info.get("is_live"):
        await bot.send_message(m.chat.id, "Livestreams are not supported.")
        return

    if info.get("_type") == "playlist":
        await bot.send_message(m.chat.id, "Playlists are not supported.")
        return

    # 🔴 Adult blocked in normal GCs
    if adult and m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and m.chat.id not in AUTHORIZED_ADULT_CHATS:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Join private group", url=ADULT_GC_LINK)
        ]])
        await bot.send_message(m.chat.id, "18+ content not allowed here.", reply_markup=kb)
        return

    duration = info.get("duration") or 0

    if adult and duration > MAX_LIMIT_ADULT:
        await bot.send_message(m.chat.id, "18+ video too long.")
        return

    if not adult and duration > SOFT_LIMIT_NORMAL:
        await bot.send_message(m.chat.id, "Video too long.")
        return

    status = await bot.send_message(m.chat.id, "Downloading…")

    base = ("a_" if adult else "n_") + secrets.token_hex(6)
    raw = f"{base}_raw.mp4"
    out = f"{base}.mp4"

    download(url, raw)

    # Recode normal only
    if not adult:
        ffmpeg_recode(raw, out)
    else:
        out = raw

    size_mb = os.path.getsize(out) / (1024 * 1024)
    if size_mb > MAX_TG_MB:
        await status.edit_text("File too large for Telegram.")
        os.remove(out)
        if raw != out and os.path.exists(raw):
            os.remove(raw)
        return

    await status.edit_text("Uploading…")

    try:
        sent = await bot.send_video(
            chat_id=m.chat.id,
            video=FSInputFile(out),
            supports_streaming=True
        )
    finally:
        if os.path.exists(out):
            os.remove(out)
        if raw != out and os.path.exists(raw):
            os.remove(raw)

    if not adult and m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        try:
            await bot.pin_chat_message(m.chat.id, sent.message_id)
        except:
            pass

    if adult:
        warn = await bot.send_message(m.chat.id, "Deleting in 10 seconds. Save now.")
        await asyncio.sleep(DELETE_ADULT_AFTER)
        for msg in (sent, warn):
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
