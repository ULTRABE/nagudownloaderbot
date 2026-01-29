import asyncio, os, tempfile, time, random, logging
from pathlib import Path
from datetime import datetime
from yt_dlp import YoutubeDL
from aiogram.types import FSInputFile

# ═══════════════════════════════════════════════════════════
# ⚙️  AUDIO HANDLER CONFIGURATION
# ═══════════════════════════════════════════════════════════

logger = logging.getLogger("NAGU_AUDIO")

# 5-6 parallel audio jobs
AUDIO_SEMAPHORE = asyncio.Semaphore(6)

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

def pick_proxy():
    return random.choice(PROXIES)

def pick_ua():
    return random.choice(USER_AGENTS)

# ═══════════════════════════════════════════════════════════
# 🎵 AUDIO DOWNLOAD OPTIONS
# ═══════════════════════════════════════════════════════════

AUDIO_OPTS = {
    "quiet": True,
    "no_warnings": False,
    "noplaylist": True,
    "format": "bestaudio/best",
    "outtmpl": "%(title)s.%(ext)s",
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "320",  # High quality audio
    }],
    "postprocessor_args": [
        "-ar", "48000",  # Sample rate
        "-ac", "2",      # Stereo
    ],
}

# ═══════════════════════════════════════════════════════════
# 🛠️ UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════

def mention(u):
    return f'<a href="tg://user?id={u.id}">{u.first_name}</a>'

def audio_caption(m, elapsed, title="Audio"):
    return (
        "╔═══════════════════════════════════════╗\n"
        "║   ⟣—◈ 𝗡𝗔𝗚𝗨 𝗔𝗨𝗗𝗜𝗢 ◈—⟢   ║\n"
        "╚═══════════════════════════════════════╝\n\n"
        f"🎵 𝗧𝗶𝘁𝗹𝗲: {title[:50]}\n"
        f"👤 𝗨𝘀𝗲𝗿: {mention(m.from_user)}\n"
        f"⚡ 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 𝗧𝗶𝗺𝗲: {elapsed:.2f}s\n"
        f"📅 𝗗𝗮𝘁𝗲: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "🔥 @nagudownloaderbot"
    )

# ═══════════════════════════════════════════════════════════
# 🎵 AUDIO DOWNLOAD HANDLER
# ═══════════════════════════════════════════════════════════

async def handle_audio(bot, m, url):
    """
    Download and send audio from supported platforms
    
    Args:
        bot: Telegram bot instance
        m: Message object
        url: Audio/video URL to extract audio from
    """
    async with AUDIO_SEMAPHORE:
        logger.info(f"🎵 Processing audio URL: {url}")
        start = time.perf_counter()

        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                
                # Configure download options
                opts = AUDIO_OPTS.copy()
                opts["outtmpl"] = str(tmp / "%(title)s.%(ext)s")
                opts["proxy"] = pick_proxy()
                opts["http_headers"] = {
                    "User-Agent": pick_ua(),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }

                # Add cookies if available
                cookie_file = "cookies_music.txt"
                if os.path.exists(cookie_file):
                    opts["cookiefile"] = cookie_file
                    logger.info(f"🎵 Using cookies from {cookie_file}")

                # Download audio
                loop = asyncio.get_running_loop()
                
                with YoutubeDL(opts) as ydl:
                    # Extract info first to get title
                    info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
                    title = info.get('title', 'Unknown')
                    
                    # Download
                    await loop.run_in_executor(None, ydl.download, [url])

                # Find the downloaded MP3 file
                mp3 = None
                for f in tmp.iterdir():
                    if f.suffix == ".mp3":
                        mp3 = f
                        break

                if not mp3:
                    logger.error("❌ No MP3 file found after download")
                    await m.answer(
                        "❌ 𝗔𝘂𝗱𝗶𝗼 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗙𝗮𝗶𝗹𝗲𝗱\n\n"
                        "Could not extract audio from the provided URL.\n"
                        "Please ensure the URL contains audio content."
                    )
                    return

                elapsed = time.perf_counter() - start
                file_size = mp3.stat().st_size / 1024 / 1024  # MB
                
                logger.info(f"✅ Audio downloaded: {title} ({file_size:.2f} MB) in {elapsed:.2f}s")

                # Send audio file
                await bot.send_audio(
                    m.chat.id,
                    FSInputFile(mp3),
                    caption=audio_caption(m, elapsed, title),
                    parse_mode="HTML",
                    title=title,
                    performer="NAGU ULTRA"
                )

        except Exception as e:
            logger.error(f"❌ Audio download failed: {e}", exc_info=True)
            await m.answer(
                f"❌ 𝗔𝘂𝗱𝗶𝗼 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗙𝗮𝗶𝗹𝗲𝗱\n\n"
                f"Error: {str(e)[:200]}\n\n"
                f"💡 Possible reasons:\n"
                f"• Invalid URL\n"
                f"• No audio available\n"
                f"• Platform restrictions\n"
                f"• Network issues"
            )
