import asyncio, os, re, subprocess, tempfile, time, requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

MAX_WORKERS = 8
queue = asyncio.Semaphore(MAX_WORKERS)

LINK_RE = re.compile(r"https?://\S+")
SPOTIFY_RE = re.compile(r"https?://open\.spotify\.com/track/\S+")

# ---------------- VIDEO CORE ----------------

BASE_YDL = {
    "quiet": True,
    "format": "bv*+ba/best",
    "merge_output_format": "mp4",
    "noplaylist": True,
    "continuedl": False,
    "nopart": True,
    "retries": 0,
    "fragment_retries": 0,
    "concurrent_fragment_downloads": 1,
    "http_chunk_size": 0,
    "nooverwrites": True,
}

def run(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def smart_download(url, out):
    opts = BASE_YDL.copy()
    opts["outtmpl"] = out
    with YoutubeDL(opts) as y:
        y.download([url])

def smart_output(src, dst):
    size_mb = os.path.getsize(src) / (1024 * 1024)

    if size_mb <= 12:
        run(["ffmpeg","-y","-i",src,"-c","copy","-movflags","+faststart",dst])
        return

    run([
        "ffmpeg","-y","-i",src,
        "-vf","scale=720:-2:flags=fast_bilinear",
        "-c:v","libvpx-vp9",
        "-b:v","380k",
        "-deadline","realtime",
        "-cpu-used","24",
        "-row-mt","1",
        "-pix_fmt","yuv420p",
        "-movflags","+faststart",
        "-c:a","libopus",
        "-b:a","32k",
        dst
    ])

def mention(u):
    name = f"{u.first_name or ''} {u.last_name or ''}".strip()
    return f'<a href="tg://user?id={u.id}">{name}</a>'

# ---------------- AUDIO CORE ----------------

AUDIO_DLP = {
    "quiet": True,
    "format": "bestaudio/best",
    "noplaylist": True,
    "postprocessors": [
        {"key": "FFmpegExtractAudio","preferredcodec": "mp3","preferredquality": "96"},
        {"key": "FFmpegMetadata"},
        {"key": "EmbedThumbnail"},
    ],
    "writethumbnail": True,
}

def yt_music_to_mp3(url, folder):
    opts = AUDIO_DLP.copy()
    opts["outtmpl"] = os.path.join(folder, "%(title)s.%(ext)s")

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title", "song")
        return os.path.join(folder, f"{title}.mp3")

def get_spotify_title(url):
    data = requests.get(f"https://open.spotify.com/oembed?url={url}", timeout=5).json()
    return data["title"]

def spotify_to_mp3(query, folder):
    opts = AUDIO_DLP.copy()
    opts["default_search"] = "ytsearch1"
    opts["outtmpl"] = os.path.join(folder, "%(title)s.%(ext)s")

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(query, download=True)
        title = info["entries"][0]["title"]
        return os.path.join(folder, f"{title}.mp3")

# ---------------- UI ----------------

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("Send video, YouTube Music or Spotify links.")

# ---------------- YT MUSIC ----------------

@dp.message(F.text.contains("music.youtube.com"))
async def yt_music_handler(message: Message):

    start = time.perf_counter()

    with tempfile.TemporaryDirectory() as tmp:
        mp3 = await asyncio.to_thread(yt_music_to_mp3, message.text, tmp)
        elapsed = (time.perf_counter() - start) * 1000

        caption = (
            f"> @nagudownloaderbot 💝\n>\n"
            f"> 𝐑𝐞𝐪𝐮𝐞𝐬𝐭𝐞𝐝 𝐛𝐲 {mention(message.from_user)}\n"
            f"> 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 𝐓𝐢𝐦𝐞 : {elapsed:.0f} ms"
        )

        await bot.send_audio(
            message.chat.id,
            FSInputFile(mp3),
            caption=caption,
            parse_mode="HTML",
            title="",
            performer=""
        )

# ---------------- SPOTIFY ----------------

@dp.message(F.text.regexp(SPOTIFY_RE))
async def spotify_handler(message: Message):

    start = time.perf_counter()

    try:
        title = get_spotify_title(message.text)
    except:
        await message.answer("❌ Spotify link invalid or expired")
        return

    with tempfile.TemporaryDirectory() as tmp:
        mp3 = await asyncio.to_thread(spotify_to_mp3, title, tmp)
        elapsed = (time.perf_counter() - start) * 1000

        caption = (
            f"> @nagudownloaderbot 💝\n>\n"
            f"> 𝐑𝐞𝐪𝐮𝐞𝐬𝐭𝐞𝐝 𝐛𝐲 {mention(message.from_user)}\n"
            f"> 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 𝐓𝐢𝐦𝐞 : {elapsed:.0f} ms"
        )

        await bot.send_audio(
            message.chat.id,
            FSInputFile(mp3),
            caption=caption,
            parse_mode="HTML",
            title="",
            performer=""
        )

# ---------------- VIDEO ----------------

@dp.message(F.text.regexp(LINK_RE))
async def video_handler(m: Message):
    async with queue:

        start_time = time.perf_counter()
        url = LINK_RE.search(m.text).group(0)

        try:
            await m.delete()
        except:
            pass

        with tempfile.TemporaryDirectory() as tmp:
            raw = os.path.join(tmp, "raw.mp4")
            final = os.path.join(tmp, "final.mp4")

            try:
                await asyncio.to_thread(smart_download, url, raw)
                await asyncio.to_thread(smart_output, raw, final)

                elapsed = (time.perf_counter() - start_time) * 1000

                caption = (
                    "@nagudownloaderbot 🤍\n\n"
                    f"𝐑𝐞𝐪𝐮𝐞𝐬𝐭𝐞𝐝 𝐛𝐲 {mention(m.from_user)}\n"
                    f"𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 𝐓𝐢𝐦𝐞 : {elapsed:.0f} ms"
                )

                await bot.send_video(
                    m.chat.id,
                    FSInputFile(final),
                    caption=caption,
                    parse_mode="HTML",
                    supports_streaming=True
                )
            except:
                pass

# ---------------- START ----------------

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
