import asyncio, os, re, secrets, subprocess, random
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ───── SAFE + FAST CORE ─────
MAX_WORKERS = 6
FRAGMENTS = 6
queue = asyncio.Semaphore(MAX_WORKERS)

LINK_RE = re.compile(r"https?://\S+")

BASE_YDL = {
    "quiet": True,
    "format": "bv*+ba/best",
    "merge_output_format": "mp4",
    "noplaylist": True,
    "concurrent_fragment_downloads": FRAGMENTS,
    "http_chunk_size": 4 * 1024 * 1024,
    "retries": 2,
    "fragment_retries": 2,
    "nopart": True,
    "nooverwrites": True,
}

# ───── PROXY POOL ─────

PROXIES = [
    "http://196.51.85.7:8800",
    "http://196.51.218.227:8800",
    "http://196.51.106.149:8800",
    "http://170.130.62.211:8800",
    "http://196.51.106.30:8800",
    "http://196.51.85.207:8800",
    "http://196.51.221.174:8800",
    "http://196.51.221.102:8800",
    "http://77.83.170.222:8800",
    "http://196.51.109.52:8800",
    "http://196.51.109.151:8800",
    "http://77.83.170.79:8800",
    "http://196.51.221.38:8800",
    "http://196.51.82.112:8800",
    "http://170.130.62.42:8800",
    "http://196.51.218.250:8800",
    "http://77.83.170.30:8800",
    "http://196.51.82.198:8800",
    "http://196.51.218.236:8800",
    "http://196.51.82.120:8800",
]


def pick_proxy():
    return random.choice(PROXIES)


# ───── COOKIE PICKER ─────

def pick_cookies(url: str):
    u = url.lower()
    if "instagram.com" in u:
        return "cookies_instagram.txt"
    if "youtube.com" in u or "youtu.be" in u:
        return "cookies_youtube.txt"
    return None


# ───── HELPERS ─────

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


# ───── SMART MULTI-STAGE DOWNLOADER ─────

def smart_download(url, out):

    # 1️⃣ Clean mode (fastest & safest)
    try:
        attempt_download(url, out)
        if os.path.exists(out):
            return
    except:
        pass

    # 2️⃣ Cookie fallback
    cookie_file = pick_cookies(url)
    if cookie_file:
        try:
            attempt_download(url, out, cookies=cookie_file)
            if os.path.exists(out):
                return
        except:
            pass

    # 3️⃣ Proxy rotation fallback
    for _ in range(4):
        try:
            attempt_download(url, out, proxy=pick_proxy())
            if os.path.exists(out):
                return
        except:
            continue

    raise RuntimeError("All methods blocked")


def sharp_compress(src, dst):
    run([
        "ffmpeg","-y","-i",src,
        "-vf","scale=720:-2:flags=lanczos",
        "-c:v","libx264",
        "-preset","veryfast",
        "-crf","27",
        "-profile:v","high",
        "-level","4.1",
        "-pix_fmt","yuv420p",
        "-movflags","+faststart",
        "-c:a","aac","-b:a","96k",
        dst
    ])


# ───── PREMIUM UI ─────

GROUP_TEXT = (
    "𝐓𝐡𝐚𝐧𝐤 𝐲𝐨𝐮 𝐟𝐨𝐫 𝐚𝐝𝐝𝐢𝐧𝐠 𝐦𝐞\n\n"
    "Send any video link and I’ll fetch it instantly."
)


@dp.message(CommandStart())
async def start(m: Message):
    user = m.from_user
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()

    welcome = (
        "⟣—◈𝐃𝐎𝐖𝐍𝐋𝐎𝐀𝐃𝐄𝐑 𝐁𝐎𝐓◈—⟢\n\n"
        f"{name}\n\n"
        "Download short-form videos instantly\n"
        "in stunning quality — delivered fast.\n\n"
        "──────────────\n"
        "Send a link to begin\n"
        "──────────────"
    )

    await m.answer(welcome)


@dp.message(F.new_chat_members)
async def added(m: Message):
    await m.answer(GROUP_TEXT)


def mention(user):
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return f'<a href="tg://user?id={user.id}">{name}</a>'


# ───── LINK HANDLER ─────

@dp.message(F.text.regexp(LINK_RE))
async def handle(m: Message):
    async with queue:

        url = LINK_RE.search(m.text).group(0)

        try:
            await m.delete()
        except:
            pass

        base = secrets.token_hex(6)
        raw = f"{base}_raw.mp4"
        final = f"{base}.mp4"

        try:
            await asyncio.to_thread(smart_download, url, raw)
            await asyncio.to_thread(sharp_compress, raw, final)

            caption = (
                "@nagudownloaderbot 🤍\n\n"
                f"𝐑𝐞𝐪𝐮𝐞𝐬𝐭𝐞𝐝 𝐛𝐲 {mention(m.from_user)}"
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

        for f in (raw, final):
            if os.path.exists(f):
                os.remove(f)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
