import asyncio, os, re, subprocess, tempfile, time, logging, random
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("NAGU")

BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

YT_COOKIES = "cookies_youtube.txt"
IG_COOKIES = "cookies_instagram.txt"

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
]

def pick_proxy(): return random.choice(PROXIES)
def pick_ua(): return random.choice(USER_AGENTS)

def resolve_pin(url):
    if "pin.it/" in url:
        return subprocess.getoutput(f"curl -Ls -o /dev/null -w '%{{url_effective}}' {url}")
    return url

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
semaphore = asyncio.Semaphore(16)

LINK_RE = re.compile(r"https?://\S+")

# ═══════════════════════════════════════════════════════════
# MINIMALIST PREMIUM UI
# ═══════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def start(m: Message):
    username = m.from_user.username if m.from_user.username else "NoUsername"
    
    await m.reply(f"""𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐓𝐨 𝐍𝐀𝐆𝐔 𝐃𝐎𝐖𝐍𝐋𝐎𝐀𝐃𝐄𝐑 ★
- - - - - - - - - - - - - - - - - - - - - - - - - - - -
₪ 𝐈𝐃 : {m.from_user.id}
₪ 𝐔𝐒𝐄𝐑 : @{username}
₪ 𝐍𝐀𝐌𝐄 : {m.from_user.first_name}
- - - - - - - - - - - - - - - - - - - - - - - - - - - -
𝐁𝐎𝐓 𝐇𝐄𝐋𝐏 𝐏𝐀𝐆𝐄 ⇁ /𝐇𝐄𝐋𝐏
- - - - - - - - - - - - - - - - - - - - - - - - - - - -
𝐎𝐖𝐍𝐄𝐑 ⇁ @bhosadih""", quote=True)

@dp.message(F.text == "/help")
async def help_command(m: Message):
    await m.reply("""𝐍𝐀𝐆𝐔 𝐃𝐎𝐖𝐍𝐋𝐎𝐀𝐃𝐄𝐑 - 𝐇𝐄𝐋𝐏 ★
- - - - - - - - - - - - - - - - - - - - - - - - - - - -
𝐒𝐔𝐏𝐏𝐎𝐑𝐓𝐄𝐃 𝐏𝐋𝐀𝐓𝐅𝐎𝐑𝐌𝐒:

📸 𝐈𝐍𝐒𝐓𝐀𝐆𝐑𝐀𝐌
   • Posts, Reels, IGTV, Stories

🎬 𝐘𝐎𝐔𝐓𝐔𝐁𝐄
   • Videos, Shorts, Streams

📌 𝐏𝐈𝐍𝐓𝐄𝐑𝐄𝐒𝐓
   • Video Pins, Idea Pins
- - - - - - - - - - - - - - - - - - - - - - - - - - - -
𝐅𝐄𝐀𝐓𝐔𝐑𝐄𝐒:
⚡ Ultra Fast (1-5s)
🎯 720p HD Quality
💾 Optimized Size
🔒 No Watermarks
- - - - - - - - - - - - - - - - - - - - - - - - - - - -
𝐔𝐒𝐀𝐆𝐄:
Just send any video link!
- - - - - - - - - - - - - - - - - - - - - - - - - - - -
𝐎𝐖𝐍𝐄𝐑 ⇁ @bhosadih""", quote=True)

def mention(u):
    return f'<a href="tg://user?id={u.id}">{u.first_name}</a>'

def caption(m, elapsed):
    return (
        f"₪ 𝐔𝐬𝐞𝐫: {mention(m.from_user)}\n"
        f"₪ 𝐓𝐢𝐦𝐞: {elapsed:.2f}s"
    )

def run(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ═══════════════════════════════════════════════════════════
# INSTAGRAM - ULTRA FAST MP4
# ═══════════════════════════════════════════════════════════

async def ig_download(url, out, use_cookies=False):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "best[height<=720][ext=mp4]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(out),
        "proxy": pick_proxy(),
        "http_headers": {"User-Agent": pick_ua()},
        "concurrent_fragment_downloads": 20,
        "http_chunk_size": 10485760,
    }
    
    if use_cookies and os.path.exists(IG_COOKIES):
        opts["cookiefile"] = IG_COOKIES
        logger.info("Using Instagram cookies (fallback)")
    
    await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))

async def handle_instagram(m, url):
    logger.info(f"IG: {url}")
    s = await bot.send_sticker(m.chat.id, IG_STICKER)
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            raw = t / "ig.mp4"
            final = t / "igf.mp4"

            # Try without cookies first
            try:
                await ig_download(url, raw, use_cookies=False)
            except:
                logger.info("IG: Retrying with cookies")
                await ig_download(url, raw, use_cookies=True)

            # Ultra fast VP9 in MP4 container
            await asyncio.to_thread(lambda: run([
                "ffmpeg", "-y", "-i", str(raw),
                "-vf", "scale=720:-2",
                "-c:v", "libvpx-vp9", "-crf", "27", "-b:v", "0",
                "-cpu-used", "8", "-row-mt", "1", "-threads", "12",
                "-deadline", "realtime", "-tile-columns", "2",
                "-c:a", "libopus", "-b:a", "64k",
                "-f", "mp4", "-movflags", "+faststart",
                str(final)
            ]))

            elapsed = time.perf_counter() - start
            await bot.delete_message(m.chat.id, s.message_id)

            sent = await bot.send_video(
                m.chat.id, FSInputFile(final),
                caption=caption(m, elapsed),
                parse_mode="HTML",
                supports_streaming=True,
                reply_to_message_id=m.message_id
            )

            if m.chat.type != "private":
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            
            logger.info(f"IG: Done in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"IG: {e}")
        await bot.delete_message(m.chat.id, s.message_id)
        await m.reply(f"❌ 𝐈𝐧𝐬𝐭𝐚𝐠𝐫𝐚𝐦 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}", quote=True)

# ═══════════════════════════════════════════════════════════
# YOUTUBE - ULTRA FAST MP4
# ═══════════════════════════════════════════════════════════

async def handle_youtube(m, url):
    logger.info(f"YT: {url}")
    s = await bot.send_sticker(m.chat.id, YT_STICKER)
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            raw = t / "yt.mp4"
            final = t / "ytf.mp4"

            opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "best[height<=720][ext=mp4]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best",
                "merge_output_format": "mp4",
                "outtmpl": str(raw),
                "proxy": pick_proxy(),
                "http_headers": {"User-Agent": pick_ua()},
                "concurrent_fragment_downloads": 20,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "web"],
                        "player_skip": ["webpage", "configs"],
                    }
                },
            }
            
            # Try without cookies first
            try:
                await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))
            except:
                if os.path.exists(YT_COOKIES):
                    logger.info("YT: Retrying with cookies")
                    opts["cookiefile"] = YT_COOKIES
                    await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))
                else:
                    raise

            # Ultra fast VP9 in MP4 container
            await asyncio.to_thread(lambda: run([
                "ffmpeg", "-y", "-i", str(raw),
                "-vf", "scale=720:-2",
                "-c:v", "libvpx-vp9", "-crf", "28", "-b:v", "0",
                "-cpu-used", "8", "-row-mt", "1", "-threads", "12",
                "-deadline", "realtime", "-tile-columns", "2",
                "-c:a", "libopus", "-b:a", "96k",
                "-f", "mp4", "-movflags", "+faststart",
                str(final)
            ]))

            elapsed = time.perf_counter() - start
            await bot.delete_message(m.chat.id, s.message_id)

            sent = await bot.send_video(
                m.chat.id, FSInputFile(final),
                caption=caption(m, elapsed),
                parse_mode="HTML",
                supports_streaming=True,
                reply_to_message_id=m.message_id
            )

            if m.chat.type != "private":
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            
            logger.info(f"YT: Done in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"YT: {e}")
        await bot.delete_message(m.chat.id, s.message_id)
        await m.reply(f"❌ 𝐘𝐨𝐮𝐓𝐮𝐛𝐞 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}", quote=True)

# ═══════════════════════════════════════════════════════════
# PINTEREST - ULTRA FAST MP4
# ═══════════════════════════════════════════════════════════

async def handle_pinterest(m, url):
    url = resolve_pin(url)
    logger.info(f"PIN: {url}")

    s = await bot.send_sticker(m.chat.id, PIN_STICKER)
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            raw = t / "pin.mp4"
            final = t / "pinf.mp4"

            opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "best/bestvideo+bestaudio",
                "merge_output_format": "mp4",
                "outtmpl": str(raw),
                "proxy": pick_proxy(),
                "http_headers": {"User-Agent": pick_ua()},
                "concurrent_fragment_downloads": 20,
            }

            await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))

            # Fast copy with MP4 optimization
            await asyncio.to_thread(lambda: run([
                "ffmpeg", "-y", "-i", str(raw),
                "-c:v", "copy", "-c:a", "copy",
                "-f", "mp4", "-movflags", "+faststart",
                str(final)
            ]))

            elapsed = time.perf_counter() - start
            await bot.delete_message(m.chat.id, s.message_id)

            sent = await bot.send_video(
                m.chat.id, FSInputFile(final),
                caption=caption(m, elapsed),
                parse_mode="HTML",
                supports_streaming=True,
                reply_to_message_id=m.message_id
            )

            if m.chat.type != "private":
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            
            logger.info(f"PIN: Done in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"PIN: {e}")
        await bot.delete_message(m.chat.id, s.message_id)
        await m.reply(f"❌ 𝐏𝐢𝐧𝐭𝐞𝐫𝐞𝐬𝐭 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}", quote=True)

# ═══════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════

@dp.message(F.text.regexp(LINK_RE))
async def handle(m: Message):
    try:
        await m.delete()
    except:
        pass

    url = m.text.strip()

    async with semaphore:
        try:
            if "instagram.com" in url.lower():
                await handle_instagram(m, url)
            elif "youtube.com" in url.lower() or "youtu.be" in url.lower():
                await handle_youtube(m, url)
            elif "pinterest.com" in url.lower() or "pin.it" in url.lower():
                await handle_pinterest(m, url)
            else:
                await m.reply("❌ 𝐔𝐧𝐬𝐮𝐩𝐩𝐨𝐫𝐭𝐞𝐝 𝐏𝐥𝐚𝐭𝐟𝐨𝐫𝐦", quote=True)
        except Exception as e:
            logger.error(f"Error: {e}")
            await m.reply(f"❌ 𝐄𝐫𝐫𝐨𝐫\n{str(e)[:100]}", quote=True)

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

async def main():
    logger.info("NAGU DOWNLOADER BOT - STARTING")
    logger.info(f"Semaphore: 16 concurrent downloads")
    logger.info(f"Proxies: {len(PROXIES)}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
