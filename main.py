import asyncio, os, re, subprocess, tempfile, time, logging, requests, random
from pathlib import Path
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("downloader")

BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

YT_COOKIES = "cookies_youtube.txt"
IG_COOKIES = "cookies_instagram.txt"

PROXIES = [
    "http://203033:JmNd95Z3vcX@196.51.85.7:8800",
    "http://203033:JmNd95Z3vcX@196.51.218.227:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.149:8800",
    "http://203033:JmNd95Z3vcX@170.130.62.211:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.30:8800",
    "http://203033:JmNd95Z3vcX@196.51.85.207:8800",
]

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
semaphore = asyncio.Semaphore(8)

VIDEO_RE = re.compile(r"https?://(?!music\.youtube|open\.spotify)\S+")
YTM_RE = re.compile(r"https?://music\.youtube\.com/\S+")
SPOTIFY_RE = re.compile(r"https?://open\.spotify\.com/track/\S+")

# ---------------- HELPERS ----------------

def pick_proxy():
    return random.choice(PROXIES)

def cookies_for(url):
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return YT_COOKIES if os.path.exists(YT_COOKIES) else None
    if "instagram.com" in u:
        return IG_COOKIES if os.path.exists(IG_COOKIES) else None
    return None

def run(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def fix_pinterest(url):
    if "pin.it/" in url:
        return subprocess.getoutput(f"curl -Ls -o /dev/null -w '%{{url_effective}}' {url}")
    return url

# ---------------- VIDEO CORE ----------------

BASE_YDL = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "concurrent_fragment_downloads": 4,
    "retries": 1,
    "fragment_retries": 1,
    "nopart": True,
    "nooverwrites": True,
    "format": (
        "bestvideo[height<=720][vcodec=vp9]+bestaudio/best/"
        "bestvideo[height<=720][vcodec^=avc]+bestaudio/best/"
        "best[height<=720][ext=mp4]/best"
    ),
    "merge_output_format": "mp4",
    "http_headers": {"User-Agent": "Mozilla/5.0"},
}

async def attempt(url, raw, proxy=None, cookies=None):
    opts = BASE_YDL.copy()
    opts["outtmpl"] = str(raw.with_suffix(".%(ext)s"))

    if proxy:
        opts["proxy"] = proxy
    if cookies:
        opts["cookiefile"] = cookies

    loop = asyncio.get_running_loop()
    with YoutubeDL(opts) as ydl:
        await loop.run_in_executor(None, ydl.download, [url])

    for ext in (".mp4", ".webm", ".mkv"):
        f = raw.with_suffix(ext)
        if f.exists():
            return f
    return None

async def smart_video(url, raw):
    url = fix_pinterest(url)
    cookies = cookies_for(url)

    # direct
    f = await attempt(url, raw)
    if f: return f

    # cookies
    if cookies:
        f = await attempt(url, raw, cookies=cookies)
        if f: return f

    # proxy
    for _ in range(2):
        f = await attempt(url, raw, proxy=pick_proxy(), cookies=cookies)
        if f: return f

    raise RuntimeError("blocked")

def optimize(src, out):
    if src.stat().st_size <= 12 * 1024 * 1024:
        run(["ffmpeg","-y","-i",src,"-c","copy","-movflags","+faststart",out])
        return

    run([
        "ffmpeg","-y","-i",src,
        "-vf","scale=720:-2:flags=fast_bilinear",
        "-c:v","libvpx-vp9","-b:v","380k",
        "-deadline","realtime","-cpu-used","5",
        "-row-mt","1","-pix_fmt","yuv420p",
        "-c:a","libopus","-b:a","32k",
        "-movflags","+faststart", out
    ])

# ---------------- MP3 CORE ----------------

AUDIO_YDL = {
    "quiet": True,
    "format": "bestaudio/best",
    "postprocessors": [
        {"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"96"},
        {"key":"FFmpegMetadata"},
        {"key":"EmbedThumbnail"},
    ],
    "writethumbnail": True,
}

def yt_music_mp3(url, folder):
    opts = AUDIO_YDL.copy()
    opts["outtmpl"] = os.path.join(folder, "%(title)s.%(ext)s")

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return os.path.join(folder, f"{info['title']}.mp3")

def spotify_title(url):
    return requests.get(f"https://open.spotify.com/oembed?url={url}",timeout=5).json()["title"]

def spotify_mp3(title, folder):
    opts = AUDIO_YDL.copy()
    opts["default_search"] = "ytsearch1"
    opts["outtmpl"] = os.path.join(folder, "%(title)s.%(ext)s")

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(title, download=True)
        return os.path.join(folder, f"{info['entries'][0]['title']}.mp3")

# ---------------- UI ----------------

def mention(u):
    return f'<a href="tg://user?id={u.id}">{u.first_name}</a>'

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("Send video, YouTube Music or Spotify links.")

# ---------------- MP3 HANDLERS ----------------

@dp.message(F.text.regexp(YTM_RE))
async def yt_music(m: Message):
    try: await m.delete()
    except: pass

    start = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        mp3 = await asyncio.to_thread(yt_music_mp3, m.text, tmp)
        elapsed = (time.perf_counter()-start)*1000

        await bot.send_audio(
            m.chat.id,
            FSInputFile(mp3),
            caption=(
                f"> @nagudownloaderbot 💝\n>\n"
                f"> Requested by {mention(m.from_user)}\n"
                f"> Response Time : {elapsed:.0f} ms"
            ),
            parse_mode="HTML",
            title="",
            performer=""
        )

@dp.message(F.text.regexp(SPOTIFY_RE))
async def spotify(m: Message):
    try: await m.delete()
    except: pass

    start = time.perf_counter()
    title = spotify_title(m.text)

    with tempfile.TemporaryDirectory() as tmp:
        mp3 = await asyncio.to_thread(spotify_mp3, title, tmp)
        elapsed = (time.perf_counter()-start)*1000

        await bot.send_audio(
            m.chat.id,
            FSInputFile(mp3),
            caption=(
                f"> @nagudownloaderbot 💝\n>\n"
                f"> Requested by {mention(m.from_user)}\n"
                f"> Response Time : {elapsed:.0f} ms"
            ),
            parse_mode="HTML",
            title="",
            performer=""
        )

# ---------------- VIDEO ----------------

@dp.message(F.text.regexp(VIDEO_RE))
async def video(m: Message):

    try: await m.delete()
    except: pass

    start = time.perf_counter()

    async with semaphore:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            raw = tmp / "raw"
            final = tmp / "final.mp4"

            try:
                raw_file = await smart_video(m.text, raw)
                await asyncio.to_thread(optimize, raw_file, final)

                elapsed = (time.perf_counter()-start)*1000

                await bot.send_video(
                    m.chat.id,
                    FSInputFile(final),
                    caption=(
                        "@nagudownloaderbot 🤍\n\n"
                        f"Requested by {mention(m.from_user)}\n"
                        f"Response Time : {elapsed:.0f} ms"
                    ),
                    parse_mode="HTML",
                    supports_streaming=True
                )

            except Exception as e:
                logger.exception(e)
                await m.answer("❌ Download failed")

# ---------------- RUN ----------------

async def main():
    logger.info("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
