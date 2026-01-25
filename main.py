# =========================
# main.py — FINAL STABLE BUILD (LOCKED)
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

# Encoding
CRF_NORMAL = "21"
CRF_ADULT = "23"
FPS_CAP = "35"

# Limits
SOFT_LIMIT_NORMAL = 10 * 60
MAX_LIMIT_ADULT = 30 * 60
TG_LIMIT_MB = 45

# Timers
DELETE_ADULT_AFTER = 10

# Adult GC invite
ADULT_GC_LINK = "https://t.me/+VUujjb34k9s2YTU1"

# Stable adult domains
ADULT_KEYWORDS = [
    "pornhub", "xhamster", "xnxx", "xvideos",
    "redtube", "youporn", "spankbang",
    "eporner", "beeg", "thisvid", "motherless",
    "hanime"
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
    return any(k in domain(url) for k in ADULT_KEYWORDS) or info.get("age_limit", 0) >= 18

def run(cmd: list):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def extract_info(url: str) -> dict:
    with YoutubeDL({
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 10,
    }) as ydl:
        return ydl.extract_info(url, download=False)

# ================= DOWNLOAD =================
def download_normal(url: str, out: str):
    with YoutubeDL({
        "outtmpl": out,
        "merge_output_format": "mp4",
        "format": "bv*+ba/best",
        "quiet": True,
        "noplaylist": True,
    }) as ydl:
        ydl.download([url])

def download_adult_720(url: str, out: str):
    with YoutubeDL({
        "outtmpl": out,
        "format": (
            "bv*[height=720][vcodec^=avc1]/"
            "bv*[height<=720][vcodec^=avc1]+ba[acodec^=mp4a]"
        ),
        "merge_output_format": "mp4",
        "concurrent_fragment_downloads": 8,
        "http_chunk_size": 10 * 1024 * 1024,
        "nopart": True,
        "quiet": True,
        "noplaylist": True,
    }) as ydl:
        ydl.download([url])

def encode(src: str, dst: str, height: int) -> bool:
    run([
        "ffmpeg", "-y", "-i", src,
        "-vf", f"scale=-2:{height},fps={FPS_CAP}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", CRF_ADULT,
        "-maxrate", "2500k",
        "-bufsize", "5000k",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        dst
    ])
    return os.path.exists(dst) and os.path.getsize(dst) > 0

# ================= AUTH =================
@dp.message(Command("auth"))
async def auth(m: Message):
    if m.from_user.id == OWNER_ID:
        AUTHORIZED_ADULT_CHATS.add(m.chat.id)
        await bot.send_message(m.chat.id, "Adult downloads enabled.")

@dp.message(Command("unauth"))
async def unauth(m: Message):
    if m.from_user.id == OWNER_ID:
        AUTHORIZED_ADULT_CHATS.discard(m.chat.id)
        await bot.send_message(m.chat.id, "Adult downloads disabled.")

# ================= HANDLER =================
@dp.message(HasURL())
async def handler(m: Message):
    urls = re.findall(r"https?://[^\s]+", m.text or "")
    if not urls:
        return
    url = urls[0]

    # Delete link immediately
    try:
        await m.delete()
    except:
        pass

    try:
        info = extract_info(url)
    except:
        return

    if info.get("is_live") or info.get("_type") == "playlist":
        return

    adult = is_adult(url, info)

    # ===== BLOCK ADULT IN UNAUTHORIZED GC =====
    if adult and m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and m.chat.id not in AUTHORIZED_ADULT_CHATS:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Use 18+ here", url=ADULT_GC_LINK)
        ]])
        await bot.send_message(m.chat.id, "Yahi pe muth marega kya dalle ?.", reply_markup=kb)
        return

    # ===== NORMAL =====
    if not adult:
        if (info.get("duration") or 0) > SOFT_LIMIT_NORMAL:
            return

        status = await bot.send_message(m.chat.id, "apke material download ho raha hai mutthal")

        base = f"n_{secrets.token_hex(6)}"
        raw = f"{base}_raw.mp4"
        out = f"{base}.mp4"

        download_normal(url, raw)

        run([
            "ffmpeg", "-y", "-i", raw,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", CRF_NORMAL,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", "128k",
            out
        ])

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
        await bot.delete_message(m.chat.id, status.message_id)
        return

    # ===== ADULT =====
    if (info.get("duration") or 0) > MAX_LIMIT_ADULT:
        return

    status = await bot.send_message(m.chat.id, "pro max mutthal apka video download hone laga hai l*du")

    base = f"a_{secrets.token_hex(6)}"
    raw = f"{base}_720.mp4"
    out540 = f"{base}_540.mp4"
    out480 = f"{base}_480.mp4"

    try:
        download_adult_720(url, raw)

        if encode(raw, out540, 540):
            final = out540
        elif encode(raw, out480, 480):
            final = out480
        else:
            raise RuntimeError

    except:
        await bot.delete_message(m.chat.id, status.message_id)
        for f in (raw, out540, out480):
            if os.path.exists(f):
                os.remove(f)
        return

    size_mb = os.path.getsize(final) / (1024 * 1024)
    parts = []

    if size_mb <= TG_LIMIT_MB:
        parts = [final]
    else:
        run([
            "ffmpeg", "-y", "-i", final,
            "-c", "copy",
            "-f", "segment",
            "-segment_time", "300",
            f"{base}_part_%03d.mp4"
        ])
        os.remove(final)
        parts = sorted(p for p in os.listdir() if p.startswith(base) and p.endswith(".mp4"))

    sent_msgs = []
    for p in parts:
        sent_msgs.append(await bot.send_document(m.chat.id, FSInputFile(p)))

    warn = await bot.send_message(m.chat.id, "This media will be removed in 10 seconds. Save it now.")
    await asyncio.sleep(DELETE_ADULT_AFTER)

    for msg in sent_msgs:
        try:
            await bot.delete_message(m.chat.id, msg.message_id)
        except:
            pass

    try:
        await bot.delete_message(m.chat.id, warn.message_id)
        await bot.delete_message(m.chat.id, status.message_id)
    except:
        pass

    for f in parts + [raw, out540, out480]:
        if os.path.exists(f):
            os.remove(f)

# ================= MAIN =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
