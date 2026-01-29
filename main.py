import asyncio, os, tempfile, time, random
from pathlib import Path

from yt_dlp import YoutubeDL
from aiogram.types import FSInputFile

# ---------------- CONFIG ----------------

AUDIO_SEMAPHORE = asyncio.Semaphore(6)

COOKIE_FILE = "cookies_music.txt"

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

def pick_proxy():
    return random.choice(PROXIES)

def pick_ua():
    return random.choice(USER_AGENTS)

# ---------------- YT-DLP AUDIO OPTS ----------------

def base_audio_opts():
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,

        "format": "bestaudio",

        "retries": 3,
        "fragment_retries": 3,

        "http_headers": {
            "User-Agent": pick_ua()
        },

        "cookiefile": COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,

        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

# ---------------- UI ----------------

def mention(u):
    return f'<a href="tg://user?id={u.id}">{u.first_name}</a>'

# ---------------- HANDLER ----------------

async def handle_audio(bot, m, url):
    async with AUDIO_SEMAPHORE:

        start = time.perf_counter()

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)

            opts = base_audio_opts()
            opts["outtmpl"] = str(tmp / "%(title)s.%(ext)s")
            opts["proxy"] = pick_proxy()

            loop = asyncio.get_running_loop()

            with YoutubeDL(opts) as ydl:
                await loop.run_in_executor(None, ydl.download, [url])

            mp3 = None
            for f in tmp.iterdir():
                if f.suffix == ".mp3":
                    mp3 = f
                    break

            if not mp3:
                await m.answer("❌ Audio download failed")
                return

            elapsed = (time.perf_counter() - start) * 1000

            caption = (
                "@nagudownloaderbot 🤍\n\n"
                f"{mention(m.from_user)}\n"
                f"𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 𝐓𝐢𝐦𝐞 : {elapsed:.0f} ms"
            )

            await bot.send_audio(
                m.chat.id,
                FSInputFile(mp3),
                caption=caption,
                parse_mode="HTML"
            )
