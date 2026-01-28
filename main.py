print("BOT STARTED")

import asyncio, os, re, subprocess, tempfile, time, logging, requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
queue = asyncio.Semaphore(8)

YT_COOKIES = "cookies_youtube.txt"
IG_COOKIES = "cookies_instagram.txt"

VIDEO_RE = re.compile(r"https?://(?!music\.youtube|open\.spotify)\S+")
YTM_RE = re.compile(r"https?://music\.youtube\.com/\S+")
SPOTIFY_RE = re.compile(r"https?://open\.spotify\.com/track/\S+")

# ───────── VIDEO CORE ─────────

BASE_YDL = {
    "quiet": True,
    "format": "bv*+ba/best",
    "merge_output_format": "mp4",
    "noplaylist": True,
    "continuedl": False,
    "nopart": True,
    "nooverwrites": True,
    "retries": 0,
    "fragment_retries": 0,
}

def run(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def smart_download(url, out):

    opts = BASE_YDL.copy()
    opts["outtmpl"] = out
    domain = url.lower()

    # cookies (CRITICAL FIX)
    if "youtube.com" in domain or "youtu.be" in domain:
        if os.path.exists(YT_COOKIES):
            opts["cookiefile"] = YT_COOKIES

    if "instagram.com" in domain:
        if os.path.exists(IG_COOKIES):
            opts["cookiefile"] = IG_COOKIES

    # segmented streams for heavy platforms
    if "youtube" in domain or "instagram" in domain:
        opts.update({
            "concurrent_fragment_downloads": 8,
            "http_chunk_size": 5 * 1024 * 1024,
            "retries": 2,
            "fragment_retries": 2,
        })

    with YoutubeDL(opts) as y:
        y.download([url])

def compress(src, dst):
    size = os.path.getsize(src) / 1024 / 1024
    if size <= 12:
        run(["ffmpeg","-y","-i",src,"-c","copy","-movflags","+faststart",dst])
        return
    run([
        "ffmpeg","-y","-i",src,
        "-vf","scale=720:-2",
        "-c:v","libvpx-vp9","-b:v","380k",
        "-deadline","realtime","-cpu-used","24",
        "-c:a","libopus","-b:a","32k",
        dst
    ])

# ───────── AUDIO CORE ─────────

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

def yt_to_mp3(url, folder):
    opts = AUDIO_YDL.copy()
    opts["outtmpl"] = os.path.join(folder, "%(title)s.%(ext)s")

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return os.path.join(folder, f"{info['title']}.mp3")

def spotify_title(url):
    return requests.get(
        f"https://open.spotify.com/oembed?url={url}", timeout=5
    ).json()["title"]

def spotify_mp3(title, folder):
    opts = AUDIO_YDL.copy()
    opts["default_search"] = "ytsearch1"
    opts["outtmpl"] = os.path.join(folder, "%(title)s.%(ext)s")

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(title, download=True)
        return os.path.join(folder, f"{info['entries'][0]['title']}.mp3")

def mention(u):
    return f'<a href="tg://user?id={u.id}">{u.first_name}</a>'

# ───────── UI ─────────

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("Send YouTube, Instagram, Pinterest, YT Music or Spotify links.")

# ───────── YT MUSIC ─────────

@dp.message(F.text.regexp(YTM_RE))
async def yt_music(m: Message):
    await m.delete()

    start = time.perf_counter()

    with tempfile.TemporaryDirectory() as tmp:
        mp3 = await asyncio.to_thread(yt_to_mp3, m.text, tmp)
        elapsed = (time.perf_counter()-start)*1000

        caption = (
            f"> @nagudownloaderbot 💝\n>\n"
            f"> Requested by {mention(m.from_user)}\n"
            f"> Response Time : {elapsed:.0f} ms"
        )

        await bot.send_audio(
            m.chat.id,
            FSInputFile(mp3),
            caption=caption,
            parse_mode="HTML"
        )

# ───────── SPOTIFY ─────────

@dp.message(F.text.regexp(SPOTIFY_RE))
async def spotify(m: Message):
    await m.delete()

    start = time.perf_counter()

    try:
        title = spotify_title(m.text)
    except:
        await m.answer("Spotify link invalid or expired ✘")
        return

    with tempfile.TemporaryDirectory() as tmp:
        mp3 = await asyncio.to_thread(spotify_mp3, title, tmp)
        elapsed = (time.perf_counter()-start)*1000

        caption = (
            f"> @nagudownloaderbot 💝\n>\n"
            f"> Requested by {mention(m.from_user)}\n"
            f"> Response Time : {elapsed:.0f} ms"
        )

        await bot.send_audio(
            m.chat.id,
            FSInputFile(mp3),
            caption=caption,
            parse_mode="HTML"
        )

# ───────── VIDEO ─────────

@dp.message(F.text.regexp(VIDEO_RE))
async def video(m: Message):
    async with queue:

        await m.delete()
        start = time.perf_counter()

        with tempfile.TemporaryDirectory() as tmp:
            raw = os.path.join(tmp, "raw.mp4")
            final = os.path.join(tmp, "final.mp4")

            try:
                await asyncio.to_thread(smart_download, m.text, raw)
                await asyncio.to_thread(compress, raw, final)

                elapsed = (time.perf_counter()-start)*1000

                caption = (
                    "@nagudownloaderbot 🤍\n\n"
                    f"Requested by {mention(m.from_user)}\n"
                    f"Response Time : {elapsed:.0f} ms"
                )

                await bot.send_video(
                    m.chat.id,
                    FSInputFile(final),
                    caption=caption,
                    parse_mode="HTML",
                    supports_streaming=True
                )
            except Exception as e:
                logging.error(e)
                await m.answer("Download failed")

# ───────── RUN ─────────

async def main():
    logging.info("Bot running")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
