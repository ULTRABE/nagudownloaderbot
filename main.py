# =========================
# main.py — FINAL MERGED UNIVERSAL YT-DLP BOT
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

DELETE_NORMAL_LINK_AFTER = 5
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

def is_adult(url: str, info: dict) -> bool:
    d = domain(url)
    if any(k in d for k in ADULT_KEYWORDS):
        return True
    if info.get("age_limit", 0) >= 18:
        return True
    return False

def run(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def extract_info(url):
    with YoutubeDL({
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 10,
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

    try:
        info = extract_info(url)
    except:
        await m.reply("Unsupported link.")
        return

    if info.get("is_live"):
        await m.reply("Livestreams are not supported.")
        return
    if info.get("_type") == "playlist":
        await m.reply("Playlists are not supported.")
        return

    adult = is_adult(url, info)

    # 🔴 HARD BLOCK adult in normal GCs
    if adult and m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and m.chat.id not in AUTHORIZED_ADULT_CHATS:
        try:
            await m.delete()
        except:
            pass

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Join private group to use 18+ content",
                url=ADULT_GC_LINK
            )]
        ])
        await m.chat.send_message("Unsupported link.", reply_markup=kb)
        return

    # ========= NORMAL =========
    if not adult:
        if (info.get("duration") or 0) > SOFT_LIMIT_NORMAL:
            await m.reply("Video is too long to download here.")
            return

        status = await m.reply("Downloading…")
        await asyncio.sleep(DELETE_NORMAL_LINK_AFTER)
        try:
            await m.delete()
        except:
            pass

        base = f"n_{secrets.token_hex(6)}"
        raw = f"{base}_raw.mp4"
        out = f"{base}.mp4"

        download(url, raw)
        await status.edit_text("Uploading…")

        run([
            "ffmpeg", "-y", "-i", raw,
            "-c:v", "libx264", "-preset", "veryfast",
            "-crf", CRF_NORMAL,
            "-maxrate", MAXRATE, "-bufsize", BUFSIZE,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "128k",
            out
        ])

        sent = await bot.send_video(
            chat_id=m.chat.id,
            video=FSInputFile(out),
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

    # ========= ADULT (AUTHORIZED GC ONLY) =========
    if (info.get("duration") or 0) > MAX_LIMIT_ADULT:
        await m.reply("18+ video is too long.")
        return

    status = await m.reply("Downloading…")
    base = f"a_{secrets.token_hex(6)}"
    raw = f"{base}.mp4"

    download(url, raw)
    await status.edit_text("Uploading…")

    sent = await bot.send_video(
        chat_id=m.chat.id,
        video=FSInputFile(raw),
        supports_streaming=True
    )

    warn = await m.reply("This media will be deleted in 10 seconds. Save it now.")

    await asyncio.sleep(DELETE_ADULT_AFTER)

    for msg in (sent, warn):
        try:
            await bot.delete_message(m.chat.id, msg.message_id)
        except:
            pass

    await m.chat.send_message("History cleared.")
    os.remove(raw)
    await status.delete()

# ================= MAIN =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
