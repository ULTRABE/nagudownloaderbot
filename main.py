import asyncio, os, re, subprocess, random, tempfile, time, shutil
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ───── VPS POWER SETTINGS ─────
MAX_WORKERS = 25
FRAGMENTS = 16
queue = asyncio.Semaphore(MAX_WORKERS)

LINK_RE = re.compile(r"https?://\S+")

# Use RAM disk if available (INSANE speedup)
RAMDISK = "/dev/shm" if os.path.exists("/dev/shm") else None

BASE_YDL = {
    "quiet": True,
    "noplaylist": True,

    "format": "bv*[ext=mp4]/best[ext=mp4]",
    "merge_output_format": "mp4",

    "concurrent_fragment_downloads": FRAGMENTS,
    "http_chunk_size": 16 * 1024 * 1024,
    "buffersize": 64 * 1024 * 1024,

    "hls_prefer_native": True,
    "hls_use_mpegts": True,

    "throttledratelimit": 10000000,

    "retries": 3,
    "fragment_retries": 3,
    "socket_timeout": 20,

    "nopart": True,
    "nooverwrites": True,
}

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

def pick_cookies(url):
    u = url.lower()
    if "instagram.com" in u:
        return "cookies_instagram.txt"
    if "youtube.com" in u or "youtu.be" in u:
        return "cookies_youtube.txt"
    return None

def run(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def attempt_download(url, out, cookies=None, proxy=None):
    opts = BASE_YDL.copy()
    opts["outtmpl"] = out
    if cookies:
        opts["cookies"] = cookies
    if proxy:
        opts["proxy"] = proxy

    with YoutubeDL(opts) as y:
        y.download([url])

def smart_download(url, out):
    try:
        attempt_download(url, out)
        if os.path.exists(out):
            return
    except:
        pass

    cookie = pick_cookies(url)
    if cookie:
        try:
            attempt_download(url, out, cookies=cookie)
            if os.path.exists(out):
                return
        except:
            pass

    for _ in range(2):
        try:
            attempt_download(url, out, proxy=pick_proxy())
            if os.path.exists(out):
                return
        except:
            continue

    raise RuntimeError("Blocked")

# ───── ULTRA FAST VP9 OUTPUT ─────

def smart_output(src, dst):
    size_mb = os.path.getsize(src) / (1024 * 1024)

    # instant path for small shorts
    if size_mb < 8:
        os.rename(src, dst)
        return

    run([
        "ffmpeg","-y","-i",src,

        "-vf","scale=720:-2",

        "-c:v","libvpx-vp9",
        "-b:v","260k",
        "-maxrate","320k",
        "-bufsize","600k",

        "-threads","0",
        "-row-mt","1",
        "-tile-columns","4",
        "-frame-parallel","1",
        "-cpu-used","32",
        "-deadline","realtime",

        "-pix_fmt","yuv420p",

        "-c:a","libopus",
        "-b:a","32k",

        "-movflags","+faststart",
        dst
    ])

# ───── UI ─────

GROUP_TEXT = (
    "𝐓𝐡𝐚𝐧𝐤 𝐲𝐨𝐮 𝐟𝐨𝐫 𝐚𝐝𝐝𝐢𝐧𝐠 𝐦𝐞\n\n"
    "Send any video link and I’ll fetch it instantly."
)

@dp.message(CommandStart())
async def start(m: Message):
    u = m.from_user
    name = f"{u.first_name or ''} {u.last_name or ''}".strip()

    await m.answer(
        "⟣—◈𝐃𝐎𝐖𝐍𝐋𝐎𝐀𝐃𝐄𝐑 𝐁𝐎𝐓◈—⟢\n\n"
        f"{name}\n\n"
        "Download short-form videos instantly\n"
        "in stunning quality — delivered fast.\n\n"
        "──────────────\n"
        "Send a link to begin\n"
        "──────────────"
    )

@dp.message(F.new_chat_members)
async def added(m: Message):
    await m.answer(GROUP_TEXT)

def mention(user):
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return f'<a href="tg://user?id={user.id}">{name}</a>'

# ───── HANDLER ─────

@dp.message(F.text.regexp(LINK_RE))
async def handle(m: Message):
    async with queue:

        start_time = time.perf_counter()
        url = LINK_RE.search(m.text).group(0)

        try:
            await m.delete()
        except:
            pass

        # RAM disk temp dir
        base_tmp = RAMDISK or tempfile.gettempdir()
        tmp = tempfile.mkdtemp(dir=base_tmp)

        raw = os.path.join(tmp, "raw.mp4")
        final = os.path.join(tmp, "final.mp4")

        try:
            await asyncio.to_thread(smart_download, url, raw)
            await asyncio.to_thread(smart_output, raw, final)

            elapsed = time.perf_counter() - start_time

            caption = (
                "@nagudownloaderbot 🤍\n\n"
                f"𝐑𝐞𝐪𝐮𝐞𝐬𝐭𝐞𝐝 𝐛𝐲 {mention(m.from_user)}\n"
                f"𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 𝐓𝐢𝐦𝐞 — {elapsed:.2f}s"
            )

            sent = await bot.send_video(
                m.chat.id,
                FSInputFile(final),
                caption=caption,
                parse_mode="HTML",
                supports_streaming=True
            )

            if m.chat.type != "private":
                try:
                    await bot.pin_chat_message(m.chat.id, sent.message_id)
                except:
                    pass

        except:
            pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
