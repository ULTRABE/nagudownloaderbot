import asyncio, os, re, secrets, subprocess, random, tempfile
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

BOT_TOKEN = os.getenv("BOT_TOKEN")

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
    "http://203033:JmNd95Z3vcX@196.51.85.7:8800",
    "http://203033:JmNd95Z3vcX@196.51.218.227:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.149:8800",
    "http://203033:JmNd95Z3vcX@170.130.62.211:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.30:8800",
    "http://203033:JmNd95Z3vcX@196.51.85.207:8800",
    "http://203033:JmNd95Z3vcX@196.51.221.174:8800",
    "http://203033:JmNd95Z3vcX@196.51.221.102:8800",
    "http://203033:JmNd95Z3vcX@77.83.170.222:8800",
    "http://203033:JmNd95Z3vcX@196.51.109.52:8800",
    "http://203033:JmNd95Z3vcX@196.51.109.151:8800",
    "http://203033:JmNd95Z3vcX@77.83.170.79:8800",
    "http://203033:JmNd95Z3vcX@196.51.221.38:8800",
    "http://203033:JmNd95Z3vcX@196.51.82.112:8800",
    "http://203033:JmNd95Z3vcX@170.130.62.42:8800",
    "http://203033:JmNd95Z3vcX@196.51.218.250:8800",
    "http://203033:JmNd95Z3vcX@77.83.170.30:8800",
    "http://203033:JmNd95Z3vcX@196.51.82.198:8800",
    "http://203033:JmNd95Z3vcX@196.51.218.236:8800",
    "http://203033:JmNd95Z3vcX@196.51.82.120:8800",
    "http://203033:JmNd95Z3vcX@196.51.221.125:8800",
    "http://203033:JmNd95Z3vcX@77.83.170.91:8800",
    "http://203033:JmNd95Z3vcX@196.51.82.59:8800",
    "http://203033:JmNd95Z3vcX@196.51.109.138:8800",
    "http://203033:JmNd95Z3vcX@170.130.62.24:8800",
    "http://203033:JmNd95Z3vcX@170.130.62.27:8800",
    "http://203033:JmNd95Z3vcX@196.51.109.8:8800",
    "http://203033:JmNd95Z3vcX@196.51.85.156:8800",
    "http://203033:JmNd95Z3vcX@196.51.218.169:8800",
    "http://203033:JmNd95Z3vcX@77.83.170.124:8800",
    "http://203033:JmNd95Z3vcX@196.51.82.106:8800",
    "http://203033:JmNd95Z3vcX@196.51.85.127:8800",
    "http://203033:JmNd95Z3vcX@170.130.62.151:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.117:8800",
    "http://203033:JmNd95Z3vcX@170.130.62.221:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.16:8800",
    "http://203033:JmNd95Z3vcX@170.130.62.223:8800",
    "http://203033:JmNd95Z3vcX@196.51.85.59:8800",
    "http://203033:JmNd95Z3vcX@170.130.62.251:8800",
    "http://203033:JmNd95Z3vcX@196.51.218.179:8800",
    "http://203033:JmNd95Z3vcX@196.51.82.238:8800",
    "http://203033:JmNd95Z3vcX@196.51.109.31:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.100:8800",
    "http://203033:JmNd95Z3vcX@77.83.170.168:8800",
    "http://203033:JmNd95Z3vcX@196.51.221.46:8800",
    "http://203033:JmNd95Z3vcX@196.51.218.60:8800",
    "http://203033:JmNd95Z3vcX@196.51.221.158:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.69:8800",
    "http://203033:JmNd95Z3vcX@196.51.109.6:8800",
    "http://203033:JmNd95Z3vcX@196.51.85.213:8800",
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

    if size_mb <= 12:
        run([
            "ffmpeg","-y","-i",src,
            "-c","copy",
            "-movflags","+faststart",
            dst
        ])
        return

    run([
        "ffmpeg","-y","-i",src,
        "-vf","scale=720:-2:flags=fast_bilinear",
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
