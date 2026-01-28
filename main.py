import asyncio, os, re, secrets, subprocess, random, tempfile
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ───── FASTER CORE ─────
MAX_WORKERS = 8          # +33% throughput safely
FRAGMENTS = 8
queue = asyncio.Semaphore(MAX_WORKERS)

LINK_RE = re.compile(r"https?://\S+")

BASE_YDL = {
    "quiet": True,
    "format": "bv*+ba/best",
    "merge_output_format": "mp4",
    "noplaylist": True,
    "concurrent_fragment_downloads": FRAGMENTS,
    "http_chunk_size": 6 * 1024 * 1024,
    "retries": 2,
    "fragment_retries": 2,
    "nopart": True,
    "nooverwrites": True,
}

PROXIES = [
    "http://196.51.85.7:8800",
    "http://196.51.218.227:8800",
    "http://196.51.106.149:8800",
    "http://170.130.62.211:8800",
    "http://196.51.106.30:8800",
    "http://196.51.85.207:8800",
]

def pick_proxy():
    return random.choice(PROXIES)


def pick_cookies(url: str):
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

    cookie_file = pick_cookies(url)
    if cookie_file:
        try:
            attempt_download(url, out, cookies=cookie_file)
            if os.path.exists(out):
                return
        except:
            pass

    for _ in range(3):
        try:
            attempt_download(url, out, proxy=pick_proxy())
            if os.path.exists(out):
                return
        except:
            continue

    raise RuntimeError("Blocked")


# ───── SMART FAST COMPRESSION ─────

def smart_output(src, dst):
    size_mb = os.path.getsize(src) / (1024 * 1024)

    # if already small → remux only (super fast)
    if size_mb <= 8:
        run([
            "ffmpeg","-y","-i",src,
            "-c","copy",
            "-movflags","+faststart",
            dst
        ])
        return

    # else compress
    run([
        "ffmpeg","-y","-i",src,
        "-vf","scale=720:-2:flags=lanczos",
        "-c:v","libx264",
        "-preset","veryfast",
        "-crf","27",
        "-pix_fmt","yuv420p",
        "-movflags","+faststart",
        "-c:a","aac","-b:a","96k",
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


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
