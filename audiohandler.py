import asyncio, os, tempfile, time, random
from pathlib import Path
from yt_dlp import YoutubeDL
from aiogram.types import FSInputFile

# 5–6 parallel audio jobs
AUDIO_SEMAPHORE = asyncio.Semaphore(6)

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

AUDIO_OPTS = {
    "quiet": True,
    "noplaylist": True,
    "format": "bestaudio",
    "outtmpl": "%(title)s.%(ext)s",

    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "192",
    }],
}

def mention(u):
    return f'<a href="tg://user?id={u.id}">{u.first_name}</a>'

async def handle_audio(bot, m, url):
    async with AUDIO_SEMAPHORE:

        start = time.perf_counter()

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            AUDIO_OPTS["outtmpl"] = str(tmp / "%(title)s.%(ext)s")
            AUDIO_OPTS["proxy"] = pick_proxy()

            loop = asyncio.get_running_loop()

            with YoutubeDL(AUDIO_OPTS) as ydl:
                await loop.run_in_executor(None, ydl.download, [url])

            mp3 = None
            for f in tmp.iterdir():
                if f.suffix == ".mp3":
                    mp3 = f
                    break

            if not mp3:
                await m.answer("❌ Audio download failed")
                return

            elapsed = (time.perf_counter() - start) * 1000

            caption = (
                "@nagudownloaderbot 🤍\n\n"
                f"{mention(m.from_user)}\n"
                f"𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 𝐓𝐢𝐦𝐞 : {elapsed:.0f} ms"
            )

            await bot.send_audio(
                m.chat.id,
                FSInputFile(mp3),
                caption=caption,
                parse_mode="HTML"
            )
