import asyncio, os, re, secrets, subprocess
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

MAX_MB = 5
FPS = 30
CRF = "23"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

ADULT_WORDS = [
    "porn","sex","xxx","hentai","nsfw","fuck","anal","boobs",
    "pussy","dick","milf","onlyfans","hardcore","18+","leaked"
]


def run(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def detect_hw():
    if subprocess.call(["ffmpeg","-hide_banner","-encoders"], stdout=subprocess.DEVNULL):
        return "cpu"
    out = subprocess.check_output(["ffmpeg","-encoders"]).decode()
    if "h264_nvenc" in out:
        return "nvenc"
    if "h264_vaapi" in out:
        return "vaapi"
    return "cpu"


HW = detect_hw()


def is_adult(info):
    if info.get("age_limit", 0) >= 18:
        return True

    text = " ".join([
        info.get("title",""),
        " ".join(info.get("tags",[]) if info.get("tags") else []),
        " ".join(info.get("categories",[]) if info.get("categories") else [])
    ]).lower()

    return sum(w in text for w in ADULT_WORDS) >= 2


def get_info(url):
    with YoutubeDL({"quiet": True, "skip_download": True}) as y:
        return y.extract_info(url, download=False)


def ultra_download(url, out):
    with YoutubeDL({
        "outtmpl": out,
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "noplaylist": True,
        "concurrent_fragment_downloads": 12,
        "http_chunk_size": 10 * 1024 * 1024,
        "nopart": True
    }) as y:
        y.download([url])


def compress(src, dst, dur):
    bits = (MAX_MB * 1024 * 1024 * 8) / max(dur, 1)
    rate = int(bits * 0.85)

    if HW == "nvenc":
        cmd = [
            "ffmpeg","-y","-i",src,
            "-vf",f"scale=-2:720,fps={FPS}",
            "-c:v","h264_nvenc","-b:v",str(rate),
            "-c:a","aac","-b:a","96k",
            "-movflags","+faststart",dst
        ]

    elif HW == "vaapi":
        cmd = [
            "ffmpeg","-y","-i",src,
            "-vf",f"format=nv12,scale=-2:720,fps={FPS}",
            "-c:v","h264_vaapi","-b:v",str(rate),
            "-c:a","aac","-b:a","96k",
            "-movflags","+faststart",dst
        ]

    else:
        cmd = [
            "ffmpeg","-y","-i",src,
            "-vf",f"scale=-2:720,fps={FPS}",
            "-c:v","libx264",
            "-preset","veryfast",
            "-crf",CRF,
            "-maxrate",str(rate),
            "-bufsize",str(rate*2),
            "-pix_fmt","yuv420p",
            "-c:a","aac","-b:a","96k",
            "-movflags","+faststart",dst
        ]

    run(cmd)


# ───── Premium Start ─────

@dp.message(CommandStart())
async def start(m: Message):
    name = m.from_user.first_name or "there"
    await m.answer(
        "𝐍𝐚𝐠𝐮 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 ⚡\n\n"
        f"Hey {name},\n\n"
        "Send a video link from supported platforms\n"
        "and I’ll fetch it instantly.\n\n"
        "⚡ Ultra fast\n"
        "🎬 High quality\n"
        "📦 Tiny size\n\n"
        "Just drop the link."
    )


# ───── Added to Group ─────

@dp.message(F.new_chat_members)
async def added(m: Message):
    await m.answer(
        "Thanks for adding me ⚡\n"
        "Send any video link and I’ll download it instantly."
    )


# ───── Main Handler ─────

@dp.message()
async def handle(m: Message):
    if not m.text:
        return

    urls = re.findall(r"https?://[^\s]+", m.text)
    if not urls:
        return

    url = urls[0]

    try:
        data = get_info(url)
    except:
        return

    if is_adult(data):
        try: await m.delete()
        except: pass
        return

    try: await m.delete()
    except: pass

    dur = data.get("duration") or 0

    base = secrets.token_hex(6)
    raw = f"{base}_raw.mp4"
    final = f"{base}.mp4"

    try:
        ultra_download(url, raw)
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
