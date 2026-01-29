import asyncio, os, re, subprocess, tempfile, time, logging, random
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("downloader")

BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

YT_COOKIES = "cookies_youtube.txt"
IG_COOKIES = "cookies_instagram.txt"

PROCESS_STICKER = "CAACAgIAAxkBAAEadEdpekZa1-2qYm-1a3dX0JmM_Z9uDgAC4wwAAjAT0Euml6TE9QhYWzgE"

PROXIES = [
    "http://203033:JmNd95Z3vcX@196.51.85.7:8800",
    "http://203033:JmNd95Z3vcX@196.51.218.227:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.149:8800",
    "http://203033:JmNd95Z3vcX@170.130.62.211:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.30:8800",
    "http://203033:JmNd95Z3vcX@196.51.85.207:8800",
]

def pick_proxy():
    return random.choice(PROXIES)

# -------- USER AGENT ROTATION --------

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.5; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/121.0.0.0 Safari/537.36",
]

def pick_ua():
    return random.choice(USER_AGENTS)

# ------------------------------------

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
semaphore = asyncio.Semaphore(8)

LINK_RE = re.compile(r"https?://\S+")

BASE_YDL = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,

    "concurrent_fragment_downloads": 8,
    "http_chunk_size": 6 * 1024 * 1024,

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
    "http_headers": {"User-Agent": pick_ua()},
}

# ---------------- helpers ----------------

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

# ---------------- download engine ----------------

async def attempt(url, raw, proxy=None, cookies=None):
    opts = BASE_YDL.copy()
    opts["outtmpl"] = str(raw.with_suffix(".%(ext)s"))

    if "pinterest.com" in url:
        opts["concurrent_fragment_downloads"] = 1
        opts["http_chunk_size"] = 0

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

async def smart_download(url, raw):
    url = fix_pinterest(url)
    cookies = cookies_for(url)

    for _ in range(3):
        f = await attempt(url, raw, proxy=pick_proxy(), cookies=cookies)
        if f:
            return f

    f = await attempt(url, raw, cookies=cookies)
    if f:
        return f

    f = await attempt(url, raw)
    if f:
        return f

    raise RuntimeError("download failed")

# ---------------- compression ----------------

def optimize(src: Path, out: Path):
    size_mb = src.stat().st_size / 1024 / 1024

    if size_mb <= 18:
        run([
            "ffmpeg","-y","-i",src,
            "-c","copy",
            "-movflags","+faststart",
            out
        ])
        return

    run([
        "ffmpeg","-y","-i",src,
        "-vf","scale=720:-2:flags=lanczos",
        "-c:v","libvpx-vp9",
        "-crf","26",
        "-b:v","0",
        "-deadline","realtime",
        "-cpu-used","8",
        "-row-mt","1",
        "-pix_fmt","yuv420p",
        "-c:a","libopus",
        "-b:a","48k",
        "-movflags","+faststart",
        out
    ])

# ---------------- UI ----------------

def mention(u):
    return f'<a href="tg://user?id={u.id}">{u.first_name}</a>'

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("⟣—◈𝗡𝗔𝗚𝗨 𝗨𝗟𝗧𝗥𝗔 𝗗𝗢𝗪𝗡𝗟𝗢𝗔𝗗𝗘𝗥◈—⟢

━━━━━━━━━━━━━━━━━━
ID ➞ {user_id}  
USER ➞ @{username}  
NAME ➞ {first_name}
━━━━━━━━━━━━━━━━━━

🚀 FASTEST VIDEO DOWNLOADER  
📥 INSTA • YT SHORTS • PINTEREST  
🎯 HQ QUALITY • LOW SIZE

━━━━━━━━━━━━━━━━━━
HELP ➞ /HELP
OWNER ➞ @bhosadih
━━━━━━━━━━━━━━━━━━")

# ---------------- main handler ----------------

@dp.message(F.text.regexp(LINK_RE))
async def handle(m: Message):

    try:
        await m.delete()
    except:
        pass

    processing = await bot.send_sticker(m.chat.id, PROCESS_STICKER)
    start = time.perf_counter()

    async with semaphore:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            raw = tmp / "raw"
            final = tmp / "final.mp4"

            try:
                url = m.text.strip()

                raw_file = await smart_download(url, raw)
                await asyncio.to_thread(optimize, raw_file, final)

                elapsed = (time.perf_counter() - start) * 1000

                await bot.delete_message(m.chat.id, processing.message_id)

                caption = (
                    "@nagudownloaderbot 🤍\n\n"
                    f"{mention(m.from_user)}\n"
                    f"𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 𝐓𝐢𝐦𝐞 : {elapsed:.0f} ms"
                )

                sent = await bot.send_video(
                    m.chat.id,
                    FSInputFile(final),
                    caption=caption,
                    parse_mode="HTML",
                    supports_streaming=True
                )

                # 📌 AUTO PIN
                if m.chat.type != "private":
                    try:
                        await bot.pin_chat_message(m.chat.id, sent.message_id)
                    except:
                        pass

            except Exception:
                await bot.delete_message(m.chat.id, processing.message_id)
                await m.answer("❌ Download failed")

# ---------------- run ----------------

async def main():
    logger.info("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
