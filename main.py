import asyncio, os, re, subprocess, tempfile, time, logging, random
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("downloader")

BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

YT_COOKIES = "cookies_youtube.txt"
IG_COOKIES = "cookies_instagram.txt"

# DIAGNOSTIC: Check if cookie files exist
logger.info("=" * 50)
logger.info("DIAGNOSTIC CHECK - Cookie Files")
logger.info("=" * 50)
for cookie_file in [YT_COOKIES, IG_COOKIES, "cookies_music.txt"]:
    exists = os.path.exists(cookie_file)
    logger.info(f"Cookie file '{cookie_file}': {'EXISTS' if exists else 'MISSING'}")
logger.info("=" * 50)

IG_STICKER = "CAACAgIAAxkBAAEadEdpekZa1-2qYm-1a3dX0JmM_Z9uDgAC4wwAAjAT0Euml6TE9QhYWzgE"
YT_STICKER = "CAACAgIAAxkBAAEaedlpez9LOhwF-tARQsD1V9jzU8iw1gACQjcAAgQyMEixyZ896jTkCDgE"
PIN_STICKER = "CAACAgIAAxkBAAEaegZpe0KJMDIkiCbudZrXhJDwBXYHqgACExIAAq3mUUhZ4G5Cm78l2DgE"

PROXIES = [
    "http://203033:JmNd95Z3vcX@196.51.85.7:8800",
    "http://203033:JmNd95Z3vcX@196.51.218.227:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.149:8800",
    "http://203033:JmNd95Z3vcX@170.130.62.211:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.30:8800",
    "http://203033:JmNd95Z3vcX@196.51.85.207:8800",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.5; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edge/121.0.0.0 Safari/537.36",
]

def pick_proxy(): return random.choice(PROXIES)
def pick_ua(): return random.choice(USER_AGENTS)

def resolve_pin(url):
    if "pin.it/" in url:
        return subprocess.getoutput(f"curl -Ls -o /dev/null -w '%{{url_effective}}' {url}")
    return url

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
semaphore = asyncio.Semaphore(8)

LINK_RE = re.compile(r"https?://\S+")

# ---------------- START ----------------

@dp.message(CommandStart())
async def start(m: Message):
    username = f"@{m.from_user.username}" if m.from_user.username else "—"

    await m.answer(f"""
◇—◈ NAGU ULTRA DOWNLOADER ◈—◇

ID ➝ {m.from_user.id}
USER ➝ {username}
NAME ➝ {m.from_user.first_name}

━━━━━━━━━━━━━━━━━━━━━━━
🚀 FAST VIDEO DOWNLOADER
📥 INSTA • YT • PINTEREST
🎯 HQ QUALITY • LOW SIZE
━━━━━━━━━━━━━━━━━━━━━━━

HELP ➝ /help
OWNER ➝ @bhosadih
""")

@dp.message(F.text == "/help")
async def help_command(m: Message):
    await m.answer("""
◇—◈ HOW TO USE ◈—◇

Simply send me a link from:
• Instagram (posts, reels, stories)
• YouTube (videos, shorts)
• Pinterest (videos, pins)

I'll download and send you the video!

━━━━━━━━━━━━━━━━━━━━━━━
📌 Supported Platforms:
✓ Instagram.com
✓ YouTube.com / Youtu.be
✓ Pinterest.com / Pin.it

⚡ Features:
• High quality downloads
• Fast processing
• Optimized file sizes
• No watermarks

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

# ==================================================
# ================= INSTAGRAM ======================
# ==================================================

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
    if os.path.exists(IG_COOKIES):
        opts["cookiefile"] = IG_COOKIES
        logger.info(f"Using Instagram cookies from {IG_COOKIES}")
    else:
        logger.warning(f"Instagram cookies file not found: {IG_COOKIES}")
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
    logger.info(f"Processing Instagram URL: {url}")
    s = await bot.send_sticker(m.chat.id, IG_STICKER)
    start = time.perf_counter()

    try:
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
            logger.info(f"Instagram download completed in {elapsed:.0f}ms")
    except Exception as e:
        logger.error(f"Instagram download failed: {e}", exc_info=True)
        await bot.delete_message(m.chat.id, s.message_id)
        await m.answer(f"❌ Instagram download failed: {str(e)}")

# ==================================================
# ================= YOUTUBE FIXED ==================
# ==================================================

async def handle_youtube(m, url):
    logger.info(f"Processing YouTube URL: {url}")
    s = await bot.send_sticker(m.chat.id, YT_STICKER)
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            raw = t / "yt.mp4"
            final = t / "ytf.mp4"

            opts = {
                "quiet": True,
                "format": "bv*[height<=720]+ba/best",
                "merge_output_format": "mp4",
                "prefer_ffmpeg": True,
                "outtmpl": str(raw),
                "proxy": pick_proxy(),
                "http_headers": {"User-Agent": pick_ua()},
                "force_ipv4": True,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "web"],
                        "player_skip": ["configs"],
                    }
                },
            }
            
            if os.path.exists(YT_COOKIES):
                opts["cookiefile"] = YT_COOKIES
                logger.info(f"Using YouTube cookies from {YT_COOKIES}")
            else:
                logger.warning(f"YouTube cookies file not found: {YT_COOKIES}")

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
            logger.info(f"YouTube download completed in {elapsed:.0f}ms")
    except Exception as e:
        logger.error(f"YouTube download failed: {e}", exc_info=True)
        await bot.delete_message(m.chat.id, s.message_id)
        await m.answer(f"❌ YouTube download failed: {str(e)}")

# ==================================================
# ================= PINTEREST FIXED =================
# ==================================================

async def handle_pinterest(m, url):
    url = resolve_pin(url)
    logger.info(f"Processing Pinterest URL: {url}")

    s = await bot.send_sticker(m.chat.id, PIN_STICKER)
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            raw = t / "pin.mp4"
            final = t / "pinf.mp4"

            opts = {
                "quiet": True,
                "format": "best",
                "merge_output_format": "mp4",
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
            logger.info(f"Pinterest download completed in {elapsed:.0f}ms")
    except Exception as e:
        logger.error(f"Pinterest download failed: {e}", exc_info=True)
        await bot.delete_message(m.chat.id, s.message_id)
        await m.answer(f"❌ Pinterest download failed: {str(e)}")

# ==================================================
# ================= ROUTER =========================
# ==================================================

@dp.message(F.text.regexp(LINK_RE))
async def handle(m: Message):
    logger.info(f"Received URL from user {m.from_user.id}: {m.text}")

    try:
        await m.delete()
    except Exception as e:
        logger.warning(f"Could not delete message: {e}")

    url = m.text.lower()

    async with semaphore:
        try:
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
        except Exception as e:
            logger.error(f"Unhandled error in message handler: {e}", exc_info=True)
            await m.answer(f"❌ An error occurred: {str(e)}")

# ---------------- RUN ----------------

async def main():
    logger.info("=" * 50)
    logger.info("BOT STARTING")
    logger.info(f"Bot Token: {BOT_TOKEN[:20]}...")
    logger.info("=" * 50)
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot failed to start: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(main())
