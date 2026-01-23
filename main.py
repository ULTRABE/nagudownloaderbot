# =========================
# main.py — FINAL (LOCKED SPEC)
# =========================

import asyncio
import logging
import os
import re
import secrets
import subprocess
import time
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher
from aiogram.filters import BaseFilter, Command
from aiogram.types import Message, FSInputFile
from aiogram.enums import ChatType
from yt_dlp import YoutubeDL

# ================= CONFIG =================
BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"
OWNER_ID = 7363967303

# Encoding (fast, small, clean)
CRF_NORMAL = "24"
CRF_ADULT = "23"
MAXRATE = "4M"
BUFSIZE = "8M"

# Limits
SOFT_LIMIT_NORMAL = 10 * 60        # 10 minutes
MAX_LIMIT_ADULT = 30 * 60          # 30 minutes
CHUNK_MAX_MB = 45                  # adult chunks
DELETE_NORMAL_LINK_AFTER = 5       # seconds
DELETE_ADULT_AFTER = 10            # seconds

# Explicit adult domains (safe, static)
ADULT_DOMAINS = [
    "pornhub", "xhamster", "xnxx", "xvideos", "redtube", "youporn",
    "spankbang", "tube8", "txxx", "eporner", "beeg", "thisvid", "motherless"
]

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

def is_adult_domain(url: str) -> bool:
    d = domain(url)
    return any(x in d for x in ADULT_DOMAINS)

def run(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def sizeof_mb(path):
    return os.path.getsize(path) / (1024 * 1024)

# ================= AUTH (ADULT ONLY) =================
AUTHORIZED_ADULT_CHATS = set()

@dp.message(Command("auth"))
async def auth(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    AUTHORIZED_ADULT_CHATS.add(m.chat.id)
    await m.reply("Adult downloads enabled in this chat.")

@dp.message(Command("unauth"))
async def unauth(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    AUTHORIZED_ADULT_CHATS.discard(m.chat.id)
    await m.reply("Adult downloads disabled in this chat.")

# ================= YT-DLP SINGLE PASS =================
def extract_info(url):
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 10,
        "nocheckcertificate": True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def download_media(url, outtmpl):
    ydl_opts = {
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "format": "bestvideo+bestaudio/best",
        "quiet": True,
        "noplaylist": True,
        "socket_timeout": 10,
        "nocheckcertificate": True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# ================= NORMAL FLOW =================
async def handle_normal(m: Message, url: str, info: dict):
    duration = info.get("duration") or 0
    if duration > SOFT_LIMIT_NORMAL:
        await m.reply("Video is too long to download here.")
        return

    await asyncio.sleep(DELETE_NORMAL_LINK_AFTER)
    try:
        await m.delete()
    except:
        pass

    base = f"n_{secrets.token_hex(6)}"
    raw = f"{base}_raw.mp4"
    out = f"{base}.mp4"

    try:
        # audio-only?
        if info.get("vcodec") == "none":
            # send as audio
            ydl_opts = {
                "outtmpl": f"{base}.%(ext)s",
                "format": "bestaudio/best",
                "quiet": True,
                "noplaylist": True,
            }
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            audio_file = next(p for p in os.listdir(".") if p.startswith(base))
            await m.chat.send_audio(FSInputFile(audio_file))
            os.remove(audio_file)
            return

        download_media(url, raw)

        run([
            "ffmpeg", "-y", "-i", raw,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", CRF_NORMAL,
            "-maxrate", MAXRATE,
            "-bufsize", BUFSIZE,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "128k",
            out
        ])

        sent = await m.chat.send_video(
            FSInputFile(out),
            caption="@nagudownloaderbot 🤍",
            supports_streaming=True
        )

        if m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            try:
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            except:
                pass
    finally:
        for f in (raw, out):
            if os.path.exists(f):
                os.remove(f)

# ================= ADULT FLOW =================
async def handle_adult(m: Message, url: str, info: dict):
    if m.chat.id not in AUTHORIZED_ADULT_CHATS:
        await m.reply("18+ content cannot be downloaded here.")
        return

    duration = info.get("duration") or 0
    if duration > MAX_LIMIT_ADULT:
        await m.reply("18+ video is too long to download here.")
        return

    base = f"a_{secrets.token_hex(6)}"
    raw = f"{base}.mp4"

    try:
        download_media(url, raw)

        # Re-encode once (720p minimum implicitly preserved by source)
        enc = f"{base}_enc.mp4"
        run([
            "ffmpeg", "-y", "-i", raw,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", CRF_ADULT,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "128k",
            enc
        ])

        # Chunk into <=45MB
        parts = []
        idx = 1
        cur = f"{base}_part_{idx}.mp4"
        run([
            "ffmpeg", "-y", "-i", enc,
            "-map", "0",
            "-fs", f"{CHUNK_MAX_MB}M",
            cur
        ])
        parts.append(cur)

        await m.reply("This media will be deleted in 10 seconds. Forward/save now.")

        sent_ids = []
        for p in parts:
            msg = await m.chat.send_video(
                FSInputFile(p),
                supports_streaming=True
            )
            sent_ids.append(msg.message_id)

        await asyncio.sleep(DELETE_ADULT_AFTER)

        # Cleanup everything
        for mid in sent_ids:
            try:
                await bot.delete_message(m.chat.id, mid)
            except:
                pass
        try:
            await m.delete()
        except:
            pass
        await m.chat.send_message("History cleared.")

    finally:
        for f in (raw, enc):
            if os.path.exists(f):
                os.remove(f)
        for p in list(filter(lambda x: x.startswith(base), os.listdir("."))):
            try:
                os.remove(p)
            except:
                pass

# ================= ROUTER =================
@dp.message(HasURL())
async def router(m: Message):
    urls = re.findall(r"https?://[^\s]+", m.text or "")
    if not urls:
        return

    url = urls[0]

    try:
        info = extract_info(url)
    except:
        await m.reply("Unsupported link. Download not possible.")
        return

    # reject playlists & livestreams
    if info.get("is_live"):
        await m.reply("Livestreams are not supported.")
        return
    if info.get("_type") == "playlist":
        await m.reply("Playlists are not supported.")
        return

    # adult vs normal
    if is_adult_domain(url) or info.get("age_limit", 0) >= 18:
        await handle_adult(m, url, info)
    else:
        await handle_normal(m, url, info)

# ================= MAIN =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
