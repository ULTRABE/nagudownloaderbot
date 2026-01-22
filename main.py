import asyncio
import logging
import re
import time
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
import yt_dlp

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- TOKEN (HARDCODE LOCALLY) ----------------
BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------------- CONSTANTS ----------------
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

MAX_SHORT_SIZE = 6 * 1024 * 1024  # 6 MB hard cap

SHORT_URL_HINTS = [
    r'instagram\.com/reel/',
    r'facebook\.com.*shorts',
    r'pinterest\.com.*short'
]

# ---------------- HELPERS ----------------
def looks_like_short_url(url: str) -> bool:
    return any(re.search(p, url.lower()) for p in SHORT_URL_HINTS)

def unique_outtmpl() -> str:
    return str(TEMP_DIR / f"video_{int(time.time() * 1000)}.%(ext)s")

async def extract_info(url: str) -> dict | None:
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception:
        return None

async def download_video(url: str) -> Path | None:
    outtmpl = unique_outtmpl()
    ydl_opts = {
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "format": "bestvideo[height<=720][fps<=30]+bestaudio/best[height<=720]"
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        # find the produced file
        prefix = Path(outtmpl.replace(".%(ext)s", ""))
        for f in TEMP_DIR.iterdir():
            if f.stem.startswith(prefix.name):
                return f
        return None
    except Exception:
        return None

async def optimize_short_video(input_path: Path) -> Path | None:
    output_path = input_path.with_suffix(".opt.mp4")
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-b:v", "900k",
        "-maxrate", "900k",
        "-bufsize", "1800k",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "96k",
        "-movflags", "+faststart",
        str(output_path)
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.communicate()
        return output_path if output_path.exists() else None
    except Exception:
        return None

async def cleanup(path: Path | None):
    if path and path.exists():
        try:
            await asyncio.to_thread(path.unlink)
        except Exception:
            pass

# ---------------- HANDLERS ----------------
@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer("Send a video link")

@dp.message(F.text)
async def video_handler(message: Message):
    url = message.text.strip()

    # delete user link
    try:
        await message.delete()
    except Exception:
        pass

    status = await message.answer("⬇️ Downloading...")

    info = await extract_info(url)
    if not info:
        try:
            await status.delete()
        except Exception:
            pass
        await message.answer("❌ Unsupported or invalid link")
        return

    duration = info.get("duration", 9999)
    is_short = duration <= 60 or looks_like_short_url(url)

    video_path = await download_video(url)

    try:
        await status.delete()
    except Exception:
        pass

    if not video_path or not video_path.exists():
        await message.answer("❌ Download failed")
        return

    # Shorts: only re-encode if size exceeds cap
    if is_short and video_path.stat().st_size > MAX_SHORT_SIZE:
        optimized = await optimize_short_video(video_path)
        if optimized:
            await cleanup(video_path)
            video_path = optimized

    uploading = await message.answer("⬆️ Uploading...")

    try:
        with open(video_path, "rb") as f:
            sent = await message.answer_video(
                video=f,
                caption="@nagudownloaderbot 🤍",
                supports_streaming=True
            )
        await bot.pin_chat_message(message.chat.id, sent.message_id)
    except Exception:
        await message.answer("❌ Failed to send video")
    finally:
        try:
            await uploading.delete()
        except Exception:
            pass
        await cleanup(video_path)

# ---------------- MAIN ----------------
async def main():
    me = await bot.get_me()
    logger.info("[INFO] Bot starting...")
    logger.info(f"[INFO] Bot username: @{me.username}")
    logger.info("[INFO] Polling started successfully")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
