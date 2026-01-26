import asyncio, os, re, secrets, subprocess
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"  # safer

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ───── SPEED CORE ─────
MAX_WORKERS = 10
FRAGMENTS = 30
queue = asyncio.Semaphore(MAX_WORKERS)

LINK_RE = re.compile(r"https?://\S+")

YDL_FAST = {
    "quiet": True,
    "format": "bv*+ba/best",
    "merge_output_format": "mp4",
    "noplaylist": True,
    "concurrent_fragment_downloads": FRAGMENTS,
    "http_chunk_size": 20 * 1024 * 1024,
    "retries": 0,
    "nopart": True,
    "nooverwrites": True,
    "cookies": "cookies.txt",
}


def run(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def fast_download(url, out):
    opts = YDL_FAST.copy()
    opts["outtmpl"] = out
    with YoutubeDL(opts) as y:
        y.download([url])


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


# ───── PREMIUM SERIF UI ─────

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
            await asyncio.to_thread(fast_download, url, raw)
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
