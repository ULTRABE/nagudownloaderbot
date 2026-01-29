import asyncio, os, re, subprocess, tempfile, time, logging, random
from pathlib import Path
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

# ═══════════════════════════════════════════════════════════
# ⚙️  LOGGING CONFIGURATION
# ═══════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("NAGU_ULTRA")

# ═══════════════════════════════════════════════════════════
# 🔐 CONFIGURATION
# ═══════════════════════════════════════════════════════════

BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

YT_COOKIES = "cookies_youtube.txt"
IG_COOKIES = "cookies_instagram.txt"

# ═══════════════════════════════════════════════════════════
# 🎨 PREMIUM STICKERS
# ═══════════════════════════════════════════════════════════

IG_STICKER = "CAACAgIAAxkBAAEadEdpekZa1-2qYm-1a3dX0JmM_Z9uDgAC4wwAAjAT0Euml6TE9QhYWzgE"
YT_STICKER = "CAACAgIAAxkBAAEaedlpez9LOhwF-tARQsD1V9jzU8iw1gACQjcAAgQyMEixyZ896jTkCDgE"
PIN_STICKER = "CAACAgIAAxkBAAEaegZpe0KJMDIkiCbudZrXhJDwBXYHqgACExIAAq3mUUhZ4G5Cm78l2DgE"

# ═══════════════════════════════════════════════════════════
# 🌐 PROXY & USER AGENT ROTATION
# ═══════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════
# 🔍 STARTUP DIAGNOSTICS
# ═══════════════════════════════════════════════════════════

logger.info("╔═══════════════════════════════════════════════════════════╗")
logger.info("║          🚀 NAGU ULTRA DOWNLOADER - INITIALIZING         ║")
logger.info("╚═══════════════════════════════════════════════════════════╝")
logger.info("")
logger.info("📋 DIAGNOSTIC CHECK - Cookie Files:")
logger.info("─" * 60)
for cookie_file in [YT_COOKIES, IG_COOKIES, "cookies_music.txt"]:
    exists = os.path.exists(cookie_file)
    size = os.path.getsize(cookie_file) if exists else 0
    status = f"✅ EXISTS ({size} bytes)" if exists else "❌ MISSING"
    logger.info(f"  {cookie_file:25s} : {status}")
logger.info("─" * 60)
logger.info("")

# ═══════════════════════════════════════════════════════════
# 🤖 BOT INITIALIZATION
# ═══════════════════════════════════════════════════════════

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
semaphore = asyncio.Semaphore(8)

LINK_RE = re.compile(r"https?://\S+")

# ═══════════════════════════════════════════════════════════
# 🎯 URL VALIDATION
# ═══════════════════════════════════════════════════════════

def validate_instagram_url(url):
    """Validate Instagram URL format"""
    patterns = [
        r'instagram\.com/p/[\w-]+',
        r'instagram\.com/reel/[\w-]+',
        r'instagram\.com/tv/[\w-]+',
        r'instagram\.com/stories/[\w.]+/\d+',
    ]
    return any(re.search(pattern, url) for pattern in patterns)

def validate_youtube_url(url):
    """Validate YouTube URL format"""
    patterns = [
        r'youtube\.com/watch\?v=[\w-]{11}',
        r'youtu\.be/[\w-]{11}',
        r'youtube\.com/shorts/[\w-]{11}',
    ]
    return any(re.search(pattern, url) for pattern in patterns)

def validate_pinterest_url(url):
    """Validate Pinterest URL format"""
    patterns = [
        r'pinterest\.com/pin/\d+',
        r'pin\.it/[\w]+',
    ]
    return any(re.search(pattern, url) for pattern in patterns)

def resolve_pin(url):
    """Resolve shortened Pinterest URLs"""
    if "pin.it/" in url:
        try:
            resolved = subprocess.getoutput(f"curl -Ls -o /dev/null -w '%{{url_effective}}' {url}")
            logger.info(f"📌 Resolved pin.it URL: {url} → {resolved}")
            return resolved
        except Exception as e:
            logger.error(f"❌ Failed to resolve pin.it URL: {e}")
            return url
    return url

# ═══════════════════════════════════════════════════════════
# 💬 COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def start(m: Message):
    username = f"@{m.from_user.username}" if m.from_user.username else "—"
    
    welcome_msg = f"""
╔═══════════════════════════════════════╗
║   ⟣—◈ 𝗡𝗔𝗚𝗨 𝗨𝗟𝗧𝗥𝗔 𝗗𝗢𝗪𝗡𝗟𝗢𝗔𝗗𝗘𝗥 ◈—⟢   ║
╚═══════════════════════════════════════╝

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  👤 𝗨𝗦𝗘𝗥 𝗜𝗡𝗙𝗢                        ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃  🆔 ID    ➜ {m.from_user.id}
┃  👤 USER  ➜ {username}
┃  📛 NAME  ➜ {m.from_user.first_name}
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  ⚡ 𝗙𝗘𝗔𝗧𝗨𝗥𝗘𝗦                         ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃  🚀 Lightning Fast Downloads        ┃
┃  📥 Instagram • YouTube • Pinterest ┃
┃  🎯 Ultra HD Quality                ┃
┃  💾 Optimized File Sizes            ┃
┃  🔒 Secure & Private                ┃
┃  ⚡ Multi-threaded Processing       ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  📌 𝗤𝗨𝗜𝗖𝗞 𝗔𝗖𝗧𝗜𝗢𝗡𝗦                    ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃  ℹ️  Help Guide    ➜ /help          ┃
┃  👨‍💻 Owner Contact ➜ @bhosadih       ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

💡 𝗧𝗜𝗣: Just send me any video link to start!
"""
    
    await m.answer(welcome_msg)
    logger.info(f"✅ User {m.from_user.id} ({m.from_user.first_name}) started the bot")

@dp.message(F.text == "/help")
async def help_command(m: Message):
    help_msg = """
╔═══════════════════════════════════════╗
║      📖 𝗛𝗢𝗪 𝗧𝗢 𝗨𝗦𝗘 𝗧𝗛𝗜𝗦 𝗕𝗢𝗧      ║
╚═══════════════════════════════════════╝

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  🎯 𝗦𝗨𝗣𝗣𝗢𝗥𝗧𝗘𝗗 𝗣𝗟𝗔𝗧𝗙𝗢𝗥𝗠𝗦              ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃                                      ┃
┃  📸 𝗜𝗡𝗦𝗧𝗔𝗚𝗥𝗔𝗠                         ┃
┃     ✓ Posts & Reels                 ┃
┃     ✓ IGTV Videos                   ┃
┃     ✓ Stories                       ┃
┃                                      ┃
┃  🎬 𝗬𝗢𝗨𝗧𝗨𝗕𝗘                          ┃
┃     ✓ Regular Videos                ┃
┃     ✓ YouTube Shorts                ┃
┃     ✓ Live Streams                  ┃
┃                                      ┃
┃  📌 𝗣𝗜𝗡𝗧𝗘𝗥𝗘𝗦𝗧                        ┃
┃     ✓ Video Pins                    ┃
┃     ✓ Idea Pins                     ┃
┃                                      ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  ⚡ 𝗞𝗘𝗬 𝗙𝗘𝗔𝗧𝗨𝗥𝗘𝗦                      ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃  🎯 Ultra HD Quality (720p-1080p)   ┃
┃  💾 Smart Compression                ┃
┃  🚀 Lightning Fast Processing        ┃
┃  🔒 No Watermarks                    ┃
┃  📊 Real-time Progress               ┃
┃  ⚡ Concurrent Downloads              ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  📝 𝗨𝗦𝗔𝗚𝗘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘𝗦                   ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃                                      ┃
┃  1️⃣ Copy video link from any        ┃
┃     supported platform               ┃
┃                                      ┃
┃  2️⃣ Send the link to this bot       ┃
┃                                      ┃
┃  3️⃣ Wait for processing (5-30s)     ┃
┃                                      ┃
┃  4️⃣ Receive your video! 🎉          ┃
┃                                      ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  ⚠️  𝗜𝗠𝗣𝗢𝗥𝗧𝗔𝗡𝗧 𝗡𝗢𝗧𝗘𝗦               ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃  • Send complete video URLs only    ┃
┃  • Private accounts may not work    ┃
┃  • Age-restricted content limited   ┃
┃  • Max file size: 50MB              ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

👨‍💻 𝗢𝘄𝗻𝗲𝗿: @bhosadih
⚡ 𝗣𝗼𝘄𝗲𝗿𝗲𝗱 𝗯𝘆: NAGU ULTRA TECHNOLOGY
"""
    
    await m.answer(help_msg)
    logger.info(f"ℹ️  User {m.from_user.id} requested help")

# ═══════════════════════════════════════════════════════════
# 🛠️ UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════

def mention(u):
    return f'<a href="tg://user?id={u.id}">{u.first_name}</a>'

def caption(m, elapsed):
    return (
        "╔═══════════════════════════════════════╗\n"
        "║   ⟣—◈ 𝗡𝗔𝗚𝗨 𝗨𝗟𝗧𝗥𝗔 ◈—⟢   ║\n"
        "╚═══════════════════════════════════════╝\n\n"
        f"👤 𝗨𝘀𝗲𝗿: {mention(m.from_user)}\n"
        f"⚡ 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 𝗧𝗶𝗺𝗲: {elapsed:.2f}s\n"
        f"📅 𝗗𝗮𝘁𝗲: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "🔥 @nagudownloaderbot"
    )

def run(cmd):
    """Execute FFmpeg command silently"""
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ═══════════════════════════════════════════════════════════
# 📸 INSTAGRAM HANDLER
# ═══════════════════════════════════════════════════════════

BASE_IG = {
    "quiet": True,
    "no_warnings": False,
    "noplaylist": True,
    "concurrent_fragment_downloads": 8,
    "http_chunk_size": 10 * 1024 * 1024,
    "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
    "merge_output_format": "mp4",
    "postprocessor_args": ["-movflags", "faststart"],
}

async def ig_download(url, out):
    opts = BASE_IG.copy()
    opts["outtmpl"] = str(out)
    opts["proxy"] = pick_proxy()
    
    if os.path.exists(IG_COOKIES):
        opts["cookiefile"] = IG_COOKIES
        logger.info(f"📸 Using Instagram cookies from {IG_COOKIES}")
    else:
        logger.warning(f"⚠️  Instagram cookies file not found: {IG_COOKIES}")
    
    opts["http_headers"] = {
        "User-Agent": pick_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Sec-Fetch-Mode": "navigate",
    }
    
    await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))

def ig_optimize(src, out):
    """Optimize Instagram video for quality and size"""
    size_mb = src.stat().st_size / 1024 / 1024
    logger.info(f"📊 Instagram video size: {size_mb:.2f} MB")
    
    if size_mb <= 20:
        # Small file - just remux
        run(["ffmpeg", "-y", "-i", str(src), "-c", "copy", "-movflags", "+faststart", str(out)])
    else:
        # Large file - compress with VP9
        run([
            "ffmpeg", "-y", "-i", str(src),
            "-vf", "scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease",
            "-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0",
            "-cpu-used", "5", "-row-mt", "1", "-threads", "4",
            "-c:a", "libopus", "-b:a", "64k",
            "-movflags", "+faststart",
            str(out)
        ])

async def handle_instagram(m, url):
    logger.info(f"📸 Processing Instagram URL: {url}")
    
    if not validate_instagram_url(url):
        await m.answer(
            "❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗜𝗻𝘀𝘁𝗮𝗴𝗿𝗮𝗺 𝗨𝗥𝗟\n\n"
            "Please send a complete Instagram post/reel URL.\n"
            "Example: https://www.instagram.com/p/ABC123xyz/"
        )
        return
    
    s = await bot.send_sticker(m.chat.id, IG_STICKER)
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            raw = t / "ig.mp4"
            final = t / "igf.mp4"

            await ig_download(url, raw)
            await asyncio.to_thread(ig_optimize, raw, final)

            elapsed = time.perf_counter() - start
            await bot.delete_message(m.chat.id, s.message_id)

            sent = await bot.send_video(
                m.chat.id, FSInputFile(final),
                caption=caption(m, elapsed),
                parse_mode="HTML",
                supports_streaming=True
            )

            if m.chat.type != "private":
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            
            logger.info(f"✅ Instagram download completed in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"❌ Instagram download failed: {e}", exc_info=True)
        await bot.delete_message(m.chat.id, s.message_id)
        await m.answer(
            f"❌ 𝗜𝗻𝘀𝘁𝗮𝗴𝗿𝗮𝗺 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗙𝗮𝗶𝗹𝗲𝗱\n\n"
            f"Error: {str(e)[:200]}\n\n"
            f"💡 Possible reasons:\n"
            f"• Private account\n"
            f"• Deleted content\n"
            f"• Login required\n"
            f"• Invalid URL format"
        )

# ═══════════════════════════════════════════════════════════
# 🎬 YOUTUBE HANDLER
# ═══════════════════════════════════════════════════════════

async def handle_youtube(m, url):
    logger.info(f"🎬 Processing YouTube URL: {url}")
    
    if not validate_youtube_url(url):
        await m.answer(
            "❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗬𝗼𝘂𝗧𝘂𝗯𝗲 𝗨𝗥𝗟\n\n"
            "Please send a complete YouTube video URL.\n"
            "Example: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
        return
    
    s = await bot.send_sticker(m.chat.id, YT_STICKER)
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            raw = t / "yt.mp4"
            final = t / "ytf.mp4"

            opts = {
                "quiet": True,
                "no_warnings": False,
                "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best",
                "merge_output_format": "mp4",
                "prefer_ffmpeg": True,
                "outtmpl": str(raw),
                "proxy": pick_proxy(),
                "http_headers": {"User-Agent": pick_ua()},
                "force_ipv4": True,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "web", "ios"],
                        "player_skip": ["configs"],
                        "skip": ["dash", "hls"],
                    }
                },
            }
            
            if os.path.exists(YT_COOKIES):
                opts["cookiefile"] = YT_COOKIES
                logger.info(f"🎬 Using YouTube cookies from {YT_COOKIES}")
            else:
                logger.warning(f"⚠️  YouTube cookies file not found: {YT_COOKIES}")

            await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))

            # Optimize with VP9 codec for better compression
            run([
                "ffmpeg", "-y", "-i", str(raw),
                "-vf", "scale='min(1920,iw)':'min(1080,ih)':force_original_aspect_ratio=decrease",
                "-c:v", "libvpx-vp9", "-crf", "31", "-b:v", "0",
                "-cpu-used", "5", "-row-mt", "1", "-threads", "4",
                "-c:a", "libopus", "-b:a", "96k",
                "-movflags", "+faststart",
                str(final)
            ])

            elapsed = time.perf_counter() - start
            await bot.delete_message(m.chat.id, s.message_id)

            sent = await bot.send_video(
                m.chat.id, FSInputFile(final),
                caption=caption(m, elapsed),
                parse_mode="HTML",
                supports_streaming=True
            )

            if m.chat.type != "private":
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            
            logger.info(f"✅ YouTube download completed in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"❌ YouTube download failed: {e}", exc_info=True)
        await bot.delete_message(m.chat.id, s.message_id)
        await m.answer(
            f"❌ 𝗬𝗼𝘂𝗧𝘂𝗯𝗲 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗙𝗮𝗶𝗹𝗲𝗱\n\n"
            f"Error: {str(e)[:200]}\n\n"
            f"💡 Possible reasons:\n"
            f"• Video unavailable/deleted\n"
            f"• Age-restricted content\n"
            f"• Region blocked\n"
            f"• Invalid video ID"
        )

# ═══════════════════════════════════════════════════════════
# 📌 PINTEREST HANDLER
# ═══════════════════════════════════════════════════════════

async def handle_pinterest(m, url):
    url = resolve_pin(url)
    logger.info(f"📌 Processing Pinterest URL: {url}")
    
    if not validate_pinterest_url(url):
        await m.answer(
            "❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗣𝗶𝗻𝘁𝗲𝗿𝗲𝘀𝘁 𝗨𝗥𝗟\n\n"
            "Please send a complete Pinterest pin URL.\n"
            "Example: https://www.pinterest.com/pin/123456789/"
        )
        return

    s = await bot.send_sticker(m.chat.id, PIN_STICKER)
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            raw = t / "pin.mp4"
            final = t / "pinf.mp4"

            opts = {
                "quiet": True,
                "no_warnings": False,
                "format": "best",
                "merge_output_format": "mp4",
                "outtmpl": str(raw),
                "concurrent_fragment_downloads": 4,
                "http_chunk_size": 10 * 1024 * 1024,
                "proxy": pick_proxy(),
                "http_headers": {
                    "User-Agent": pick_ua(),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            }

            await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))

            # Fast copy with streaming optimization
            run(["ffmpeg", "-y", "-i", str(raw), "-c", "copy", "-movflags", "+faststart", str(final)])

            elapsed = time.perf_counter() - start
            await bot.delete_message(m.chat.id, s.message_id)

            sent = await bot.send_video(
                m.chat.id, FSInputFile(final),
                caption=caption(m, elapsed),
                parse_mode="HTML",
                supports_streaming=True
            )

            if m.chat.type != "private":
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            
            logger.info(f"✅ Pinterest download completed in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"❌ Pinterest download failed: {e}", exc_info=True)
        await bot.delete_message(m.chat.id, s.message_id)
        await m.answer(
            f"❌ 𝗣𝗶𝗻𝘁𝗲𝗿𝗲𝘀𝘁 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗙𝗮𝗶𝗹𝗲𝗱\n\n"
            f"Error: {str(e)[:200]}\n\n"
            f"💡 Possible reasons:\n"
            f"• Invalid pin URL\n"
            f"• Content deleted\n"
            f"• Not a video pin\n"
            f"• Access restricted"
        )

# ═══════════════════════════════════════════════════════════
# 🔀 MESSAGE ROUTER
# ═══════════════════════════════════════════════════════════

@dp.message(F.text.regexp(LINK_RE))
async def handle(m: Message):
    logger.info(f"📨 Received URL from user {m.from_user.id} ({m.from_user.first_name}): {m.text}")

    try:
        await m.delete()
    except Exception as e:
        logger.warning(f"⚠️  Could not delete message: {e}")

    url = m.text.strip()

    async with semaphore:
        try:
            if "instagram.com" in url.lower():
                await handle_instagram(m, url)
                return

            if "youtube.com" in url.lower() or "youtu.be" in url.lower():
                await handle_youtube(m, url)
                return

            if "pinterest.com" in url.lower() or "pin.it" in url.lower():
                await handle_pinterest(m, url)
                return

            await m.answer(
                "❌ 𝗨𝗻𝘀𝘂𝗽𝗽𝗼𝗿𝘁𝗲𝗱 𝗣𝗹𝗮𝘁𝗳𝗼𝗿𝗺\n\n"
                "Supported platforms:\n"
                "📸 Instagram\n"
                "🎬 YouTube\n"
                "📌 Pinterest\n\n"
                "Send /help for more information."
            )
        except Exception as e:
            logger.error(f"❌ Unhandled error in message handler: {e}", exc_info=True)
            await m.answer(
                f"❌ 𝗔𝗻 𝗘𝗿𝗿𝗼𝗿 𝗢𝗰𝗰𝘂𝗿𝗿𝗲𝗱\n\n"
                f"Error: {str(e)[:200]}\n\n"
                f"Please try again or contact @bhosadih"
            )

# ═══════════════════════════════════════════════════════════
# 🚀 MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════

async def main():
    logger.info("╔═══════════════════════════════════════════════════════════╗")
    logger.info("║              🚀 BOT STARTING - POLLING MODE              ║")
    logger.info("╚═══════════════════════════════════════════════════════════╝")
    logger.info(f"🔑 Bot Token: {BOT_TOKEN[:25]}...")
    logger.info(f"⚙️  Semaphore Limit: 8 concurrent downloads")
    logger.info(f"🌐 Proxies Available: {len(PROXIES)}")
    logger.info(f"🔄 User Agents Available: {len(USER_AGENTS)}")
    logger.info("─" * 60)
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Bot failed to start: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(main())
