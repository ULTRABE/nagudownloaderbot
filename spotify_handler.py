import asyncio, os, tempfile, time, logging, random, zipfile
from pathlib import Path
from yt_dlp import YoutubeDL
from aiogram.types import FSInputFile

logger = logging.getLogger("NAGU_SPOTIFY")

MUSIC_SEMAPHORE = asyncio.Semaphore(6)

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

MUSIC_STICKER = "CAACAgIAAxkBAAEaegZpe0KJMDIkiCbudZrXhJDwBXYHqgACExIAAq3mUUhZ4G5Cm78l2DgE"

def mention(u):
    return f'<a href="tg://user?id={u.id}">{u.first_name}</a>'

# ═══════════════════════════════════════════════════════════
# SPOTIFY PLAYLIST DOWNLOADER
# ═══════════════════════════════════════════════════════════

async def download_spotify_playlist(bot, m, url):
    """Download entire Spotify playlist"""
    async with MUSIC_SEMAPHORE:
        logger.info(f"SPOTIFY PLAYLIST: {url}")
        s = await bot.send_sticker(m.chat.id, MUSIC_STICKER)
        start = time.perf_counter()

        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                
                opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "format": "bestaudio/best",
                    "outtmpl": str(tmp / "%(title)s.%(ext)s"),
                    "proxy": pick_proxy(),
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "320",
                    }],
                    "retries": 3,
                    "fragment_retries": 3,
                }
                
                # Add cookies if available
                if os.path.exists("cookies_music.txt"):
                    opts["cookiefile"] = "cookies_music.txt"
                
                # Download playlist
                with YoutubeDL(opts) as ydl:
                    info = await asyncio.to_thread(lambda: ydl.extract_info(url, download=True))
                    playlist_title = info.get('title', 'Spotify Playlist')
                
                # Get all MP3 files
                mp3_files = list(tmp.glob("*.mp3"))
                
                if not mp3_files:
                    await bot.delete_message(m.chat.id, s.message_id)
                    await m.answer("❌ 𝐍𝐨 𝐬𝐨𝐧𝐠𝐬 𝐝𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐝")
                    return
                
                await bot.delete_message(m.chat.id, s.message_id)
                
                # Send each song to DM
                for mp3 in mp3_files:
                    try:
                        await bot.send_audio(
                            m.from_user.id,
                            FSInputFile(mp3),
                            title=mp3.stem,
                            performer="NAGU DOWNLOADER"
                        )
                        logger.info(f"Sent to DM: {mp3.name}")
                    except Exception as e:
                        logger.error(f"Failed to send {mp3.name}: {e}")
                
                # Create ZIP for group chat
                zip_path = tmp / f"{playlist_title}.zip"
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for mp3 in mp3_files:
                        zipf.write(mp3, mp3.name)
                
                elapsed = time.perf_counter() - start
                
                # Send ZIP to group chat
                await bot.send_document(
                    m.chat.id,
                    FSInputFile(zip_path),
                    caption=(
                        f"𝐒𝐏𝐎𝐓𝐈𝐅𝐘 𝐏𝐋𝐀𝐘𝐋𝐈𝐒𝐓 ★\n"
                        f"- - - - - - - - - - - - - - - - - - - - - - - - - - - -\n"
                        f"₪ 𝐔𝐬𝐞𝐫: {mention(m.from_user)}\n"
                        f"₪ 𝐒𝐨𝐧𝐠𝐬: {len(mp3_files)}\n"
                        f"₪ 𝐓𝐢𝐦𝐞: {elapsed:.2f}s"
                    ),
                    parse_mode="HTML"
                )
                
                logger.info(f"SPOTIFY: {len(mp3_files)} songs in {elapsed:.2f}s")
                
        except Exception as e:
            logger.error(f"SPOTIFY: {e}")
            try:
                await bot.delete_message(m.chat.id, s.message_id)
            except:
                pass
            await m.answer(f"❌ 𝐒𝐩𝐨𝐭𝐢𝐟𝐲 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}")

# ═══════════════════════════════════════════════════════════
# SINGLE SONG SEARCH (/mp3 command)
# ═══════════════════════════════════════════════════════════

async def search_and_download_song(bot, m, query):
    """Search and download single song"""
    async with MUSIC_SEMAPHORE:
        logger.info(f"MP3 SEARCH: {query}")
        s = await bot.send_sticker(m.chat.id, MUSIC_STICKER)
        start = time.perf_counter()

        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                
                opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "format": "bestaudio/best",
                    "outtmpl": str(tmp / "%(title)s.%(ext)s"),
                    "proxy": pick_proxy(),
                    "default_search": "ytsearch",
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "320",
                    }],
                }
                
                # Search and download first result
                with YoutubeDL(opts) as ydl:
                    await asyncio.to_thread(lambda: ydl.download([f"ytsearch1:{query}"]))
                
                # Find MP3
                mp3 = None
                for f in tmp.iterdir():
                    if f.suffix == ".mp3":
                        mp3 = f
                        break
                
                if not mp3:
                    await bot.delete_message(m.chat.id, s.message_id)
                    await m.answer("❌ 𝐒𝐨𝐧𝐠 𝐧𝐨𝐭 𝐟𝐨𝐮𝐧𝐝")
                    return
                
                elapsed = time.perf_counter() - start
                await bot.delete_message(m.chat.id, s.message_id)
                
                # Send to chat (not DM)
                await bot.send_audio(
                    m.chat.id,
                    FSInputFile(mp3),
                    caption=(
                        f"𝐌𝐏𝟑 𝐃𝐎𝐖𝐍𝐋𝐎𝐀𝐃 ★\n"
                        f"- - - - - - - - - - - - - - - - - - - - - - - - - - - -\n"
                        f"₪ 𝐔𝐬𝐞𝐫: {mention(m.from_user)}\n"
                        f"₪ 𝐓𝐢𝐦𝐞: {elapsed:.2f}s"
                    ),
                    parse_mode="HTML",
                    title=mp3.stem,
                    performer="NAGU DOWNLOADER"
                )
                
                logger.info(f"MP3: {mp3.name} in {elapsed:.2f}s")
                
        except Exception as e:
            logger.error(f"MP3: {e}")
            try:
                await bot.delete_message(m.chat.id, s.message_id)
            except:
                pass
            await m.answer(f"❌ 𝐌𝐏𝟑 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}")
