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
MAXRATE = "3M"
BUFSIZE = "6M"

SOFT_LIMIT_NORMAL = 10 * 60
MAX_LIMIT_ADULT = 30 * 60

DELETE_ADULT_AFTER = 10

ADULT_GC_LINK = "https://t.me/+5BX6H7j4osVjOWZl"

ADULT_KEYWORDS = [
    "pornhub", "xhamster", "xnxx", "xvideos", "redtube",
    "youporn", "spankbang", "tube8", "eporner",
    "beeg", "thisvid", "motherless",
    "hanime", "hentai"
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

def compress(src, out, crf):
    subprocess.run([
        "ffmpeg", "-y", "-i", src,
        "-c:v", "libx264", "-preset", "veryfast",
        "-crf", crf,
        "-maxrate", MAXRATE, "-bufsize", BUFSIZE,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "128k",
        out
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def chunk_video(src):
    out_pattern = src.replace(".mp4", "_part%02d.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-i", src,
        "-map", "0",
        "-c", "copy",
        "-f", "segment",
        "-segment_time", "45",
        "-reset_timestamps", "1",
        out_pattern
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return sorted(
        f for f in os.listdir(".")
        if f.startswith(os.path.basename(src).replace(".mp4", "_part"))
    )

# ================= AUTH =================
@dp.message(Command("auth"))
async def auth(m: Message):
    if m.from_user.id == OWNER_ID:
        AUTHORIZED_ADULT_CHATS.add(m.chat.id)
        await m.answer("Adult downloads enabled here.")

@dp.message(Command("unauth"))
async def unauth(m: Message):
    if m.from_user.id == OWNER_ID:
        AUTHORIZED_ADULT_CHATS.discard(m.chat.id)
        await m.answer("Adult downloads disabled here.")

# ================= HANDLER =================
@dp.message(HasURL())
async def handler(m: Message):
    url = re.findall(r"https?://[^\s]+", m.text or "")[0]

    # DELETE LINK IMMEDIATELY
    try:
        await m.delete()
    except:
        pass

    try:
        info = extract_info(url)
    except:
        await m.answer("Unsupported link.")
        return

    if info.get("is_live") or info.get("_type") == "playlist":
        await m.answer("Unsupported content.")
        return

    adult = is_adult(url, info)

    # BLOCK ADULT IN UNAUTHORIZED GROUPS
    if adult and m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and m.chat.id not in AUTHORIZED_ADULT_CHATS:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Join 18+ Group", url=ADULT_GC_LINK)]
        ])
        await m.answer("18+ content is restricted here.", reply_markup=kb)
        return

    # ================= NORMAL =================
    if not adult:
        if (info.get("duration") or 0) > SOFT_LIMIT_NORMAL:
            await m.answer("Video too long.")
            return

        status = await m.answer("Downloading…")

        base = f"n_{secrets.token_hex(6)}"
        raw = f"{base}_raw.mp4"
        out = f"{base}.mp4"

        download(url, raw)
        compress(raw, out, CRF_NORMAL)

        await status.edit_text("Uploading…")

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

    # ================= ADULT =================
    if (info.get("duration") or 0) > MAX_LIMIT_ADULT:
        await m.answer("18+ video too long.")
        return

    status = await m.answer("Downloading…")

    base = f"a_{secrets.token_hex(6)}"
    raw = f"{base}_raw.mp4"
    out = f"{base}.mp4"

    download(url, raw)
    compress(raw, out, CRF_ADULT)

    sent_msgs = []

    try:
        msg = await bot.send_video(
            m.chat.id,
            FSInputFile(out),
            supports_streaming=True
        )
        sent_msgs.append(msg)
    except:
        parts = chunk_video(out)
        for p in parts:
            msg = await bot.send_document(m.chat.id, FSInputFile(p))
            sent_msgs.append(msg)
            os.remove(p)

    warn = await m.answer("This media will be deleted in 10 seconds.")
    await asyncio.sleep(DELETE_ADULT_AFTER)

    for msg in sent_msgs + [warn, status]:
        try:
            await bot.delete_message(m.chat.id, msg.message_id)
        except:
            pass

    os.remove(raw)
    if os.path.exists(out):
        os.remove(out)

# ================= MAIN =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
