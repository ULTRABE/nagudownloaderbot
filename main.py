import asyncio, os, re, subprocess, tempfile, time, logging, requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

queue = asyncio.Semaphore(8)

VIDEO_RE = re.compile(r"https?://(?!music\.youtube|open\.spotify)\S+")
YTM_RE = re.compile(r"https?://music\.youtube\.com/\S+")
SPOTIFY_RE = re.compile(r"https?://open\.spotify\.com/track/\S+")

# ---------------- VIDEO ----------------

BASE_YDL = {
    "quiet": True,
    "format": "bv*+ba/best",
    "merge_output_format": "mp4",
    "noplaylist": True,
    "retries": 0,
    "fragment_retries": 0,
    "concurrent_fragment_downloads": 1,
    "nopart": True,
}

def run(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def download_video(url, folder):
    out = os.path.join(folder, "%(title)s.%(ext)s")
    opts = BASE_YDL.copy()
    opts["outtmpl"] = out

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

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

# ---------------- AUDIO ----------------

AUDIO_YDL = {
    "quiet": True,
    "format": "bestaudio/best",
    "postprocessors": [
        {"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"96"},
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
    return requests.get(f"https://open.spotify.com/oembed?url={url}",timeout=5).json()["title"]

def spotify_mp3(title, folder):
    opts = AUDIO_YDL.copy()
    opts["default_search"] = "ytsearch1"
    opts["outtmpl"] = os.path.join(folder, "%(title)s.%(ext)s")

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(title, download=True)
        return os.path.join(folder, f"{info['entries'][0]['title']}.mp3")

def mention(u):
    return f'<a href="tg://user?id={u.id}">{u.first_name}</a>'

# ---------------- START ----------------

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("Send video, YouTube Music or Spotify links.")

# -------- YOUTUBE MUSIC --------

@dp.message(F.text.regexp(YTM_RE))
async def yt_music(m: Message):
    start = time.perf_counter()

    with tempfile.TemporaryDirectory() as tmp:
        mp3 = await asyncio.to_thread(yt_to_mp3, m.text, tmp)
        elapsed = (time.perf_counter()-start)*1000

        caption = (
            f"> @nagudownloaderbot 💝\n>\n"
            f"> Requested by {mention(m.from_user)}\n"
            f"> Response Time : {elapsed:.0f} ms"
        )

        await bot.send_audio(m.chat.id, FSInputFile(mp3), caption=caption, parse_mode="HTML")

# -------- SPOTIFY --------

@dp.message(F.text.regexp(SPOTIFY_RE))
async def spotify(m: Message):
    start = time.perf_counter()

    try:
        title = spotify_title(m.text)
    except:
        await m.answer("Spotify link invalid")
        return

    with tempfile.TemporaryDirectory() as tmp:
        mp3 = await asyncio.to_thread(spotify_mp3, title, tmp)
        elapsed = (time.perf_counter()-start)*1000

        caption = (
            f"> @nagudownloaderbot 💝\n>\n"
            f"> Requested by {mention(m.from_user)}\n"
            f"> Response Time : {elapsed:.0f} ms"
        )

        await bot.send_audio(m.chat.id, FSInputFile(mp3), caption=caption, parse_mode="HTML")

# -------- VIDEO --------

@dp.message(F.text.regexp(VIDEO_RE))
async def video(m: Message):
    async with queue:

        start = time.perf_counter()

        with tempfile.TemporaryDirectory() as tmp:
            try:
                raw = await asyncio.to_thread(download_video, m.text, tmp)
                final = os.path.join(tmp, "final.mp4")

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

# ---------------- RUN ----------------

async def main():
    logging.info("Bot running")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
