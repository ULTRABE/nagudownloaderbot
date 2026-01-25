import asyncio, os, re, secrets, subprocess
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ───── Performance tuning ─────
MAX_WORKERS = 6          # burst queue
FPS = 30
TARGET_QUALITY = 720

queue = asyncio.Semaphore(MAX_WORKERS)

ADULT_WORDS = [
    "porn","sex","xxx","hentai","nsfw","fuck","anal","boobs",
    "pussy","dick","milf","onlyfans","hardcore","18+","leaked"
]


def run(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def is_adult(info):
    if info.get("age_limit", 0) >= 18:
        return True

    text = " ".join([
        info.get("title",""),
        " ".join(info.get("tags",[]) or []),
        " ".join(info.get("categories",[]) or [])
    ]).lower()

    return sum(w in text for w in ADULT_WORDS) >= 2


def fetch_info(url):
    with YoutubeDL({
        "quiet": True,
        "skip_download": True,
        "nocheckcertificate": True,
        "ignoreerrors": True,
        "extractor_args": {"generic": ["impersonate"]},
    }) as y:
        return y.extract_info(url, download=False)


def fast_download(url, out):
    with YoutubeDL({
        "outtmpl": out,
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "noplaylist": True,
        "concurrent_fragment_downloads": 16,
        "http_chunk_size": 10 * 1024 * 1024,
        "retries": 2,
        "nopart": True,
        "nooverwrites": True
    }) as y:
        y.download([url])


def compress(src, dst, dur):
    # adaptive bitrate → sharp quality per MB
    target_bitrate = int((6_000_000 * 8) / max(dur, 3))

    run([
        "ffmpeg","-y","-i",src,
        "-vf",f"scale=-2:{TARGET_QUALITY},fps={FPS}",
        "-c:v","libx264",
        "-preset","veryfast",
        "-crf","22",
        "-maxrate",str(target_bitrate),
        "-bufsize",str(target_bitrate * 2),
        "-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","96k",
        "-movflags","+faststart",
        dst
    ])


# ───── Premium start ─────

@dp.message(CommandStart())
async def start(m: Message):
    name = m.from_user.first_name or "there"
    await m.answer(
        "𝐍𝐚𝐠𝐮 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 ⚡\n\n"
        f"Hey {name},\n\n"
        "Send a video link and I’ll download it instantly.\n\n"
        "⚡ Super fast\n"
        "🎬 High quality\n"
        "📦 Optimized size\n\n"
        "Just drop a link."
    )


# ───── When added to GC ─────

@dp.message(F.new_chat_members)
async def added(m: Message):
    await m.answer(
        "Thanks for adding me ⚡\n"
        "Send any video link and I’ll fetch it instantly."
    )


# ───── Link detection (GC + DM) ─────

LINK_RE = re.compile(r"https?://\S+")


@dp.message(F.text.regexp(LINK_RE))
async def handle(m: Message):
    async with queue:

        url = LINK_RE.search(m.text).group(0)

        try:
            info = fetch_info(url)
        except:
            return

        if not info:
            return

        if is_adult(info):
            try: await m.delete()
            except: pass
            return

        try: await m.delete()
        except: pass

        dur = info.get("duration") or 0

        base = secrets.token_hex(6)
        raw = f"{base}_raw.mp4"
        final = f"{base}.mp4"

        try:
            fast_download(url, raw)
            compress(raw, final, dur)

            caption = (
                "@nagudownloaderbot 🤍\n"
                f"requested by {m.from_user.first_name}"
            )

            sent = await bot.send_video(
                m.chat.id,
                FSInputFile(final),
                caption=caption,
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
