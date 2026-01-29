import asyncio, os, re, subprocess, tempfile, time, logging, random
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("downloader")

BOT_TOKEN = "YOUR_TOKEN_HERE"

YT_COOKIES = "cookies_youtube.txt"
IG_COOKIES = "cookies_instagram.txt"

IG_STICKER = "CAACAgIAAxkBAAEadEdpekZa1-2qYm-1a3dX0JmM_Z9uDgAC4wwAAjAT0Euml6TE9QhYWzgE"
YT_STICKER = "AAMCAgADGQEAARp522l7P1Wp_U-CiCU7THebf6IkN6I1AAIjNgACYSe4S1bC7rHUeRQIAQAHbQADOAQ"
PIN_STICKER = "AAMCAgADGQEAARp512l7Px_cOFGuSWcBXOHw0AtPhie2AAL8EgAC6-HxSDg7yavyVWq2AQAHbQADOAQ"

PROXIES = [
    "http://203033:JmNd95Z3vcX@196.51.85.7:8800",
    "http://203033:JmNd95Z3vcX@196.51.218.227:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.149:8800",
    "http://203033:JmNd95Z3vcX@170.130.62.211:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.30:8800",
    "http://203033:JmNd95Z3vcX@196.51.85.207:8800",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.5; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/121.0.0.0 Safari/537.36",
]

def pick_proxy(): return random.choice(PROXIES)
def pick_ua(): return random.choice(USER_AGENTS)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
semaphore = asyncio.Semaphore(8)

LINK_RE = re.compile(r"https?://\S+")

# ---------------- START MESSAGE ----------------

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(f"""
◇—◈ NAGU ULTRA DOWNLOADER ◈—◇

ID ➝ {m.from_user.id}
USER ➝ @{m.from_user.username or "NoUsername"}
NAME ➝ {m.from_user.first_name}

━━━━━━━━━━━━━━━
🚀 FAST VIDEO DOWNLOADER
📥 INSTA • YT • PINTEREST
🎯 HQ QUALITY • LOW SIZE
━━━━━━━━━━━━━━━

HELP ➝ /HELP
OWNER ➝ @bhosadih
""")

# ---------------- COMMON ----------------

def mention(u):
    return f'<a href="tg://user?id={u.id}">{u.first_name}</a>'

def caption(m, elapsed):
    return (
        "@nagudownloaderbot 🤍\n\n"
        f"{mention(m.from_user)}\n"
        f"𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 𝐓𝐢𝐦𝐞 : {elapsed:.0f} ms"
    )

def run(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ==========================================================
# ================== INSTAGRAM (UNCHANGED) =================
# ==========================================================

BASE_IG = {
    "quiet": True,
    "noplaylist": True,
    "concurrent_fragment_downloads": 8,
    "http_chunk_size": 6 * 1024 * 1024,
    "format": "bestvideo[height<=720]+bestaudio/best",
    "merge_output_format": "mp4",
}

async def ig_download(url, out):
    opts = BASE_IG.copy()
    opts["outtmpl"] = str(out)
    opts["proxy"] = pick_proxy()
    opts["cookiefile"] = IG_COOKIES
    opts["http_headers"] = {"User-Agent": pick_ua()}
    await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))

def ig_optimize(src, out):
    size = src.stat().st_size / 1024 / 1024
    if size <= 18:
        run(["ffmpeg","-y","-i",src,"-c","copy",out])
    else:
        run([
            "ffmpeg","-y","-i",src,
            "-vf","scale=720:-2",
            "-c:v","libvpx-vp9","-crf","26","-b:v","0",
            "-cpu-used","8","-row-mt","1",
            "-c:a","libopus","-b:a","48k",
            out
        ])

async def handle_instagram(m, url):
    s = await bot.send_sticker(m.chat.id, IG_STICKER)
    start = time.perf_counter()

    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        raw = t / "ig.mp4"
        final = t / "igf.mp4"

        await ig_download(url, raw)
        await asyncio.to_thread(ig_optimize, raw, final)

        elapsed = (time.perf_counter() - start) * 1000
        await bot.delete_message(m.chat.id, s.message_id)

        sent = await bot.send_video(
            m.chat.id, FSInputFile(final),
            caption=caption(m, elapsed),
            parse_mode="HTML",
            supports_streaming=True
        )

        if m.chat.type != "private":
            await bot.pin_chat_message(m.chat.id, sent.message_id)

# ==========================================================
# ======================= YOUTUBE ==========================
# ==========================================================

async def handle_youtube(m, url):
    s = await bot.send_sticker(m.chat.id, YT_STICKER)
    start = time.perf_counter()

    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        raw = t / "yt.mp4"
        final = t / "ytf.mp4"

        opts = {
            "quiet": True,
            "format": "bestvideo[height<=1080]+bestaudio/best",
            "merge_output_format": "mp4",
            "outtmpl": str(raw),
            "proxy": pick_proxy(),
            "cookiefile": YT_COOKIES,
            "http_headers": {"User-Agent": pick_ua()},
        }

        await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))

        run([
            "ffmpeg","-y","-i",raw,
            "-vf","scale=1280:-2",
            "-c:v","libvpx-vp9","-crf","28","-b:v","0",
            "-cpu-used","8","-row-mt","1",
            "-c:a","libopus","-b:a","48k",
            final
        ])

        elapsed = (time.perf_counter() - start) * 1000
        await bot.delete_message(m.chat.id, s.message_id)

        sent = await bot.send_video(
            m.chat.id, FSInputFile(final),
            caption=caption(m, elapsed),
            parse_mode="HTML",
            supports_streaming=True
        )

        if m.chat.type != "private":
            await bot.pin_chat_message(m.chat.id, sent.message_id)

# ==========================================================
# ====================== PINTEREST =========================
# ==========================================================

async def handle_pinterest(m, url):
    s = await bot.send_sticker(m.chat.id, PIN_STICKER)
    start = time.perf_counter()

    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        raw = t / "pin.mp4"
        final = t / "pinf.mp4"

        opts = {
            "quiet": True,
            "format": "best",
            "outtmpl": str(raw),
            "concurrent_fragment_downloads": 1,
            "http_chunk_size": 0,
            "proxy": pick_proxy(),
            "http_headers": {"User-Agent": pick_ua()},
        }

        await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))

        run(["ffmpeg","-y","-i",raw,"-c","copy",final])

        elapsed = (time.perf_counter() - start) * 1000
        await bot.delete_message(m.chat.id, s.message_id)

        sent = await bot.send_video(
            m.chat.id, FSInputFile(final),
            caption=caption(m, elapsed),
            parse_mode="HTML",
            supports_streaming=True
        )

        if m.chat.type != "private":
            await bot.pin_chat_message(m.chat.id, sent.message_id)

# ==========================================================
# ======================== ROUTER ==========================
# ==========================================================

@dp.message(F.text.regexp(LINK_RE))
async def handle(m: Message):

    try:
        await m.delete()
    except:
        pass

    url = m.text.lower()

    async with semaphore:

        if "instagram.com" in url:
            await handle_instagram(m, url)
            return

        if "youtube.com" in url or "youtu.be" in url:
            await handle_youtube(m, url)
            return

        if "pinterest.com" in url or "pin.it" in url:
            await handle_pinterest(m, url)
            return

        await m.answer("❌ Unsupported link")

# ---------------- RUN ----------------

async def main():
    logger.info("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
