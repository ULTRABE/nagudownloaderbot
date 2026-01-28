import asyncio, os, re, subprocess, tempfile, time, logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

queue = asyncio.Semaphore(6)

YT_COOKIES = "cookies_youtube.txt"
IG_COOKIES = "cookies_instagram.txt"

URL_RE = re.compile(r"https?://\S+")

# ---------------- MODERN yt-dlp CONFIG ----------------

def build_opts(url, out):

    opts = {
        "quiet": True,
        "noplaylist": True,
        "outtmpl": out,

        # IMPORTANT for YouTube 2026
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web", "ios"]
            }
        },

        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
    }

    domain = url.lower()

    if "youtube.com" in domain or "youtu.be" in domain:
        if os.path.exists(YT_COOKIES):
            opts["cookiefile"] = YT_COOKIES

    if "instagram.com" in domain:
        if os.path.exists(IG_COOKIES):
            opts["cookiefile"] = IG_COOKIES

    return opts


def download(url, out):
    opts = build_opts(url, out)

    with YoutubeDL(opts) as ydl:
        ydl.download([url])


# ---------------- FAST COMPRESS ----------------

def compress(src, dst):
    size = os.path.getsize(src) / 1024 / 1024

    if size <= 12:
        subprocess.run(
            ["ffmpeg","-y","-i",src,"-c","copy","-movflags","+faststart",dst],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return

    subprocess.run([
        "ffmpeg","-y","-i",src,
        "-vf","scale=720:-2",
        "-c:v","libvpx-vp9","-b:v","380k",
        "-deadline","realtime","-cpu-used","8",
        "-c:a","libopus","-b:a","32k",
        dst
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def mention(u):
    return f'<a href="tg://user?id={u.id}">{u.first_name}</a>'


# ---------------- UI ----------------

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("Send YouTube, Instagram or Pinterest link.")

# ---------------- MAIN VIDEO HANDLER ----------------

@dp.message(F.text.regexp(URL_RE))
async def handle(m: Message):

    await m.delete()

    start = time.perf_counter()

    async with queue:
        with tempfile.TemporaryDirectory() as tmp:

            raw = os.path.join(tmp, "raw.mp4")
            final = os.path.join(tmp, "final.mp4")

            try:
                await asyncio.to_thread(download, m.text, raw)
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
                logging.exception(e)
                await m.answer("Download failed (platform blocked or private video)")

# ---------------- RUN ----------------

async def main():
    logging.info("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
