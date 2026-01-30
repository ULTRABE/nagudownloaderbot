import asyncio, os, re, subprocess, tempfile, time, logging, random, glob
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, FSInputFile
from yt_dlp import YoutubeDL

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("NAGU")

BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"

# Spotify API (from environment variables)
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

# Cookie files and folders
IG_COOKIES = "cookies_instagram.txt"
YT_COOKIES_FOLDER = "yt cookies"
YT_MUSIC_COOKIES_FOLDER = "yt music cookies"

IG_STICKER = "CAACAgIAAxkBAAEadEdpekZa1-2qYm-1a3dX0JmM_Z9uDgAC4wwAAjAT0Euml6TE9QhYWzgE"
YT_STICKER = "CAACAgIAAxkBAAEaedlpez9LOhwF-tARQsD1V9jzU8iw1gACQjcAAgQyMEixyZ896jTkCDgE"
PIN_STICKER = "CAACAgIAAxkBAAEaegZpe0KJMDIkiCbudZrXhJDwBXYHqgACExIAAq3mUUhZ4G5Cm78l2DgE"
MUSIC_STICKER = "CAACAgIAAxkBAAEaegZpe0KJMDIkiCbudZrXhJDwBXYHqgACExIAAq3mUUhZ4G5Cm78l2DgE"

PROXIES = [
    "http://203033:JmNd95Z3vcX@196.51.85.7:8800",
    "http://203033:JmNd95Z3vcX@196.51.218.227:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.149:8800",
    "http://203033:JmNd95Z3vcX@170.130.62.211:8800",
    "http://203033:JmNd95Z3vcX@196.51.106.30:8800",
    "http://203033:JmNd95Z3vcX@196.51.85.207:8800",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]

def pick_proxy(): return random.choice(PROXIES)
def pick_ua(): return random.choice(USER_AGENTS)

# Cookie rotation system
def get_random_cookie(folder):
    """Get random cookie file from folder"""
    if not os.path.exists(folder):
        return None
    cookies = glob.glob(f"{folder}/*.txt")
    if not cookies:
        return None
    return random.choice(cookies)

def resolve_pin(url):
    if "pin.it/" in url:
        return subprocess.getoutput(f"curl -Ls -o /dev/null -w '%{{url_effective}}' {url}")
    return url

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
semaphore = asyncio.Semaphore(16)
MUSIC_SEMAPHORE = asyncio.Semaphore(2)  # Reduced from 6 to 2 to protect cookies

LINK_RE = re.compile(r"https?://\S+")

# ═══════════════════════════════════════════════════════════
# MINIMALIST PREMIUM UI
# ═══════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def start(m: Message):
    username = f"@{m.from_user.username}" if m.from_user.username else "No Username"
    
    await m.reply(f"""
╔══════════════════════════╗
║   NAGU DOWNLOADER BOT    ║
╚══════════════════════════╝

USER INFORMATION
├─ ID: {m.from_user.id}
├─ Username: {username}
└─ Name: {m.from_user.first_name}

COMMANDS
├─ /help - View all features
├─ /mp3 - Download music
└─ Send any link to download

═══════════════════════════
Owner: @bhosadih
═══════════════════════════""", quote=True)

@dp.message(F.text == "/help")
async def help_command(m: Message):
    await m.reply("""
╔══════════════════════════╗
║    BOT HELP & FEATURES   ║
╚══════════════════════════╝

VIDEO DOWNLOAD
├─ Instagram: Posts, Reels, Stories
├─ YouTube: Videos, Shorts, Streams
└─ Pinterest: Video Pins
   >> Just send the link!

MUSIC DOWNLOAD
├─ /mp3 [song name]
│  └─ Search & download any song
│     192kbps MP3 quality
│
└─ Spotify Playlists
   └─ Send Spotify URL
      Downloads all songs to DM

FEATURES
├─ Ultra Fast (1-7s)
├─ HD Quality (720p)
├─ Small File Size
├─ No Watermarks
└─ High Quality Audio

═══════════════════════════
Owner: @bhosadih
═══════════════════════════""")
𝐎𝐖𝐍𝐄𝐑 ⇁ @bhosadih""", quote=True)

def mention(u):
    return f'<a href="tg://user?id={u.id}">{u.first_name}</a>'

def caption(m, elapsed):
    return (
        f"₪ 𝐔𝐬𝐞𝐫: {mention(m.from_user)}\n"
        f"₪ 𝐓𝐢𝐦𝐞: {elapsed:.2f}s"
    )

def run(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ═══════════════════════════════════════════════════════════
# INSTAGRAM - ULTRA FAST MP4
# ═══════════════════════════════════════════════════════════

async def ig_download(url, out, use_cookies=False):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "best[height<=720][ext=mp4]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(out),
        "proxy": pick_proxy(),
        "http_headers": {"User-Agent": pick_ua()},
        "concurrent_fragment_downloads": 20,
        "http_chunk_size": 10485760,
    }
    
    if use_cookies and os.path.exists(IG_COOKIES):
        opts["cookiefile"] = IG_COOKIES
        logger.info("Using Instagram cookies (fallback)")
    
    await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))

def ig_optimize(src, out):
    """OLD FAST PIPELINE - instant remux if small, fast VP9 if large"""
    size_mb = src.stat().st_size / 1024 / 1024
    logger.info(f"IG: {size_mb:.2f} MB")
    
    if size_mb <= 18:
        # PATH 1: INSTANT REMUX (NO RE-ENCODE)
        logger.info("IG: Fast copy (<=18MB)")
        run(["ffmpeg", "-y", "-i", str(src), "-c", "copy", str(out)])
    else:
        # PATH 2: FAST HIGH COMPRESSION
        logger.info("IG: Fast VP9 compression (>18MB)")
        run([
            "ffmpeg", "-y", "-i", str(src),
            "-vf", "scale=720:-2",
            "-c:v", "libvpx-vp9", "-crf", "26", "-b:v", "0",
            "-cpu-used", "8", "-row-mt", "1",
            "-pix_fmt", "yuv420p",
            "-c:a", "libopus", "-b:a", "48k",
            "-movflags", "+faststart",
            str(out)
        ])

async def handle_instagram(m, url):
    logger.info(f"IG: {url}")
    s = await bot.send_sticker(m.chat.id, IG_STICKER)
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            raw = t / "ig.mp4"
            final = t / "igf.mp4"

            # Try without cookies first
            try:
                await ig_download(url, raw, use_cookies=False)
            except:
                logger.info("IG: Retrying with cookies")
                await ig_download(url, raw, use_cookies=True)

            # OLD FAST PIPELINE
            await asyncio.to_thread(ig_optimize, raw, final)

            elapsed = time.perf_counter() - start
            try:
                await bot.delete_message(m.chat.id, s.message_id)
            except:
                pass

            sent = await bot.send_video(
                m.chat.id, FSInputFile(final),
                caption=caption(m, elapsed),
                parse_mode="HTML",
                supports_streaming=True
            )

            if m.chat.type != "private":
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            
            logger.info(f"IG: Done in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"IG: {e}")
        try:
            await bot.delete_message(m.chat.id, s.message_id)
        except:
            pass
        await m.answer(f"❌ 𝐈𝐧𝐬𝐭𝐚𝐠𝐫𝐚𝐦 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}")

# ═══════════════════════════════════════════════════════════
# YOUTUBE - FAST VP9 WITH BITRATE
# ═══════════════════════════════════════════════════════════

async def handle_youtube(m, url):
    logger.info(f"YT: {url}")
    s = await bot.send_sticker(m.chat.id, YT_STICKER)
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            raw = t / "yt.mp4"
            final = t / "ytf.mp4"

            opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "best[height<=720][ext=mp4]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best",
                "merge_output_format": "mp4",
                "outtmpl": str(raw),
                "proxy": pick_proxy(),
                "http_headers": {
                    "User-Agent": pick_ua(),
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "DNT": "1",
                },
                "socket_timeout": 30,
                "retries": 3,
                "concurrent_fragment_downloads": 20,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "web"],
                        "player_skip": ["webpage", "configs"],
                    }
                },
            }
            
            # Try without cookies first, then with rotation
            try:
                await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))
            except:
                cookie_file = get_random_cookie(YT_COOKIES_FOLDER)
                if cookie_file:
                    logger.info(f"YT: Using cookie {cookie_file}")
                    opts["cookiefile"] = cookie_file
                    await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))
                else:
                    raise

            # VP9 with bitrate (up to 12MB)
            await asyncio.to_thread(lambda: run([
                "ffmpeg", "-y", "-i", str(raw),
                "-vf", "scale=720:-2",
                "-c:v", "libvpx-vp9", "-b:v", "1200k", "-maxrate", "1500k", "-bufsize", "2400k",
                "-cpu-used", "4", "-row-mt", "1",
                "-pix_fmt", "yuv420p",
                "-c:a", "libopus", "-b:a", "128k",
                "-movflags", "+faststart",
                str(final)
            ]))

            elapsed = time.perf_counter() - start
            try:
                await bot.delete_message(m.chat.id, s.message_id)
            except:
                pass

            sent = await bot.send_video(
                m.chat.id, FSInputFile(final),
                caption=caption(m, elapsed),
                parse_mode="HTML",
                supports_streaming=True
            )

            if m.chat.type != "private":
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            
            logger.info(f"YT: Done in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"YT: {e}")
        try:
            await bot.delete_message(m.chat.id, s.message_id)
        except:
            pass
        await m.answer(f"❌ 𝐘𝐨𝐮𝐓𝐮𝐛𝐞 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}")

# ═══════════════════════════════════════════════════════════
# PINTEREST - PERFECT (UNCHANGED)
# ═══════════════════════════════════════════════════════════

async def handle_pinterest(m, url):
    url = resolve_pin(url)
    logger.info(f"PIN: {url}")

    s = await bot.send_sticker(m.chat.id, PIN_STICKER)
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            raw = t / "pin.mp4"
            final = t / "pinf.mp4"

            opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "best/bestvideo+bestaudio",
                "merge_output_format": "mp4",
                "outtmpl": str(raw),
                "proxy": pick_proxy(),
                "http_headers": {"User-Agent": pick_ua()},
                "concurrent_fragment_downloads": 20,
            }

            await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))

            # Fast copy with MP4 optimization
            await asyncio.to_thread(lambda: run([
                "ffmpeg", "-y", "-i", str(raw),
                "-c:v", "copy", "-c:a", "copy",
                "-movflags", "+faststart",
                str(final)
            ]))

            elapsed = time.perf_counter() - start
            try:
                await bot.delete_message(m.chat.id, s.message_id)
            except:
                pass

            sent = await bot.send_video(
                m.chat.id, FSInputFile(final),
                caption=caption(m, elapsed),
                parse_mode="HTML",
                supports_streaming=True
            )

            if m.chat.type != "private":
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            
            logger.info(f"PIN: Done in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"PIN: {e}")
        try:
            await bot.delete_message(m.chat.id, s.message_id)
        except:
            pass
        await m.answer(f"❌ 𝐏𝐢𝐧𝐭𝐞𝐫𝐞𝐬𝐭 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}")

# ═══════════════════════════════════════════════════════════
# SPOTIFY PLAYLIST DOWNLOADER (IMPROVED WITH YT-DLP)
# ═══════════════════════════════════════════════════════════

async def download_single_track(track_info, tmp_dir, cookie_file, retry_count=0):
    """Download a single track with proper metadata and thumbnail"""
    try:
        query = f"{track_info['artist']} {track_info['title']}"
        logger.info(f"Downloading: {query}")
        
        # Add delay before download to avoid rate limiting (3-5 seconds)
        await asyncio.sleep(random.uniform(3.0, 5.0))
        
        opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
            "outtmpl": str(tmp_dir / "%(title)s.%(ext)s"),
            "proxy": pick_proxy(),
            "http_headers": {
                "User-Agent": pick_ua(),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            },
            "default_search": "ytsearch1",
            "writethumbnail": True,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                },
                {
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": False,
                },
                {
                    "key": "FFmpegMetadata",
                    "add_metadata": True,
                }
            ],
            "postprocessor_args": [
                "-ar", "44100",
                "-ac", "2",
                "-b:a", "192k",
            ],
        }
        
        if cookie_file:
            opts["cookiefile"] = cookie_file
        
        with YoutubeDL(opts) as ydl:
            info = await asyncio.to_thread(lambda: ydl.extract_info(f"ytsearch1:{query}", download=True))
            
            # Find the downloaded MP3
            for f in tmp_dir.iterdir():
                if f.suffix == ".mp3" and f.stat().st_size > 0:
                    return {
                        'file': f,
                        'title': track_info['title'],
                        'artist': track_info['artist'],
                        'size_mb': f.stat().st_size / 1024 / 1024
                    }
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to download {track_info['title']}: {e}")
        
        # Retry with different cookie if first attempt fails
        if retry_count < 1:
            logger.info(f"Retrying {track_info['title']} with different cookie...")
            await asyncio.sleep(5)  # Wait before retry
            new_cookie = get_random_cookie(YT_MUSIC_COOKIES_FOLDER)
            return await download_single_track(track_info, tmp_dir, new_cookie, retry_count + 1)
        
        return None

def create_progress_bar(current, total, length=10):
    """Create a text-based progress bar"""
    filled = int(length * current / total)
    bar = '█' * filled + '░' * (length - filled)
    percent = int(100 * current / total)
    return f"[{bar}] {percent}%"

async def download_spotify_playlist(m, url):
    """Download Spotify playlist using spotdl directly"""
    logger.info(f"SPOTIFY: {url}")
    
    # Check if Spotify credentials are set
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        await m.answer("[ X ] Spotify API not configured")
        return
    
    # Phase 1: Processing
    status_msg = await m.answer("""
╔══════════════════════════╗
║   SPOTIFY PLAYLIST       ║
╚══════════════════════════╝

PHASE 1/3: Processing
[░░░░░░░░░░] 0%

Status: Initializing...""")
    start = time.perf_counter()
    
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            
            # Phase 2: Downloading
            await status_msg.edit_text("""
╔══════════════════════════╗
║   SPOTIFY PLAYLIST       ║
╚══════════════════════════╝

PHASE 2/3: Downloading
[███░░░░░░░] 33%

Status: Downloading songs...""")
            
            # Use spotdl to download entire playlist
            cmd = [
                "spotdl",
                "download",
                url,
                "--client-id", SPOTIFY_CLIENT_ID,
                "--client-secret", SPOTIFY_CLIENT_SECRET,
                "--output", str(tmp),
                "--format", "mp3",
                "--bitrate", "192k",
                "--threads", "1",
                "--print-errors",
            ]
            
            logger.info(f"Running spotdl download...")
            result = await asyncio.to_thread(
                lambda: subprocess.run(cmd, capture_output=True, text=True)
            )
            
            if result.returncode != 0:
                logger.error(f"spotdl failed: {result.stderr}")
                await status_msg.edit_text(f"[ X ] Spotify Failed\n{result.stderr[:100]}")
                return
            
            # Find all downloaded MP3 files
            mp3_files = list(tmp.glob("*.mp3"))
            
            if not mp3_files:
                await status_msg.edit_text("[ X ] No songs downloaded")
                return
            
            total = len(mp3_files)
            
            # Phase 3: Sending to DM
            await status_msg.edit_text(f"""
╔══════════════════════════╗
║   SPOTIFY PLAYLIST       ║
╚══════════════════════════╝

PHASE 3/3: Sending to DM
[██████░░░░] 66%

Status: Sending {total} songs...""")
            
            sent = 0
            failed = 0
            
            # Send each song to DM (without caption)
            for i, mp3 in enumerate(mp3_files, 1):
                try:
                    # Extract artist and title from filename
                    filename = mp3.stem
                    if ' - ' in filename:
                        artist, title = filename.split(' - ', 1)
                    else:
                        artist = "Unknown Artist"
                        title = filename
                    
                    file_size = mp3.stat().st_size / 1024 / 1024
                    
                    # Send without caption
                    await bot.send_audio(
                        m.from_user.id,
                        FSInputFile(mp3),
                        title=title,
                        performer=artist
                    )
                    sent += 1
                    logger.info(f"DM: {title} by {artist} ({file_size:.1f}MB)")
                    
                    # Update progress every 5 songs
                    if i % 5 == 0 or i == total:
                        progress_bar = create_progress_bar(sent, total)
                        try:
                            await status_msg.edit_text(f"""
╔══════════════════════════╗
║   SPOTIFY PLAYLIST       ║
╚══════════════════════════╝

PHASE 3/3: Sending to DM
{progress_bar}

Status: Sent {sent}/{total} songs""")
                        except:
                            pass
                    
                    # Small delay between sends
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Failed to send {mp3.name}: {e}")
                    failed += 1
        
            elapsed = time.perf_counter() - start
            
            # Final status in group
            await status_msg.edit_text(f"""
╔══════════════════════════╗
║   PLAYLIST COMPLETED     ║
╚══════════════════════════╝

{mention(m.from_user)}

SUMMARY
├─ Total Songs: {total}
├─ Sent to DM: {sent}
├─ Failed: {failed}
└─ Time: {elapsed:.1f}s

All songs sent to your DM!""", parse_mode="HTML")
            
            logger.info(f"SPOTIFY: {sent} songs in {elapsed:.2f}s")
        
    except Exception as e:
        logger.error(f"SPOTIFY: {e}")
        try:
            await status_msg.edit_text(f"[ X ] Spotify Failed\n{str(e)[:100]}")
        except:
            await m.answer(f"[ X ] Spotify Failed\n{str(e)[:100]}")

# ═══════════════════════════════════════════════════════════
# MP3 SEARCH COMMAND (WITH COOKIE ROTATION)
# ═══════════════════════════════════════════════════════════

async def search_and_download_song(m, query):
    """Search and download single song with proper metadata and thumbnail"""
    async with MUSIC_SEMAPHORE:
        logger.info(f"MP3: {query}")
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
                    "http_headers": {
                        "User-Agent": pick_ua(),
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "DNT": "1",
                    },
                    "default_search": "ytsearch1",
                    "writethumbnail": True,
                    "socket_timeout": 30,
                    "retries": 3,
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        },
                        {
                            "key": "EmbedThumbnail",
                            "already_have_thumbnail": False,
                        },
                        {
                            "key": "FFmpegMetadata",
                            "add_metadata": True,
                        }
                    ],
                    "postprocessor_args": [
                        "-ar", "44100",
                        "-ac", "2",
                        "-b:a", "192k",
                    ],
                }
                
                # Use random cookie from yt_music_cookies folder
                cookie_file = get_random_cookie(YT_MUSIC_COOKIES_FOLDER)
                if cookie_file:
                    opts["cookiefile"] = cookie_file
                    logger.info(f"MP3: Using cookie {cookie_file}")
                
                # Search and download
                with YoutubeDL(opts) as ydl:
                    info = await asyncio.to_thread(lambda: ydl.extract_info(f"ytsearch1:{query}", download=True))
                
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
                
                # Extract metadata
                entry = info['entries'][0] if 'entries' in info else info
                title = entry.get('title', mp3.stem)
                artist = entry.get('artist') or entry.get('uploader', 'Unknown Artist')
                file_size = mp3.stat().st_size / 1024 / 1024
                
                elapsed = time.perf_counter() - start
                await bot.delete_message(m.chat.id, s.message_id)
                
                # Send to chat
                await bot.send_audio(
                    m.chat.id,
                    FSInputFile(mp3),
                    caption=(
                        f"𝐌𝐏𝟑 𝐃𝐎𝐖𝐍𝐋𝐎𝐀𝐃 ★\n"
                        f"- - - - - - - - - - - - - - - - - - - - - - - - - - - -\n"
                        f"🎵 {title}\n"
                        f"🎤 {artist}\n"
                        f"💾 {file_size:.1f}MB\n"
                        f"₪ 𝐔𝐬𝐞𝐫: {mention(m.from_user)}\n"
                        f"₪ 𝐓𝐢𝐦𝐞: {elapsed:.2f}s"
                    ),
                    parse_mode="HTML",
                    title=title,
                    performer=artist
                )
                
                logger.info(f"MP3: {title} by {artist} ({file_size:.1f}MB) in {elapsed:.2f}s")
                
        except Exception as e:
            logger.error(f"MP3: {e}")
            try:
                await bot.delete_message(m.chat.id, s.message_id)
            except:
                pass
            await m.answer(f"❌ 𝐌𝐏𝟑 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}")

@dp.message(Command("mp3"))
async def mp3_command(m: Message):
    query = m.text.replace("/mp3", "").strip()
    if not query:
        await m.answer("𝐔𝐬𝐚𝐠𝐞: /mp3 song name")
        return
    await search_and_download_song(m, query)

# ═══════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════

@dp.message(F.text.regexp(LINK_RE))
async def handle(m: Message):
    url = m.text.strip()

    # Delete user's link after 5 seconds
    async def delete_link_later():
        await asyncio.sleep(5)
        try:
            await m.delete()
            logger.info("Deleted user's link after 5s")
        except:
            pass
    
    asyncio.create_task(delete_link_later())

    async with semaphore:
        try:
            if "instagram.com" in url.lower():
                await handle_instagram(m, url)
            elif "youtube.com" in url.lower() or "youtu.be" in url.lower():
                await handle_youtube(m, url)
            elif "pinterest.com" in url.lower() or "pin.it" in url.lower():
                await handle_pinterest(m, url)
            elif "spotify.com" in url.lower():
                await download_spotify_playlist(m, url)
            else:
                await m.answer("❌ 𝐔𝐧𝐬𝐮𝐩𝐩𝐨𝐫𝐭𝐞𝐝 𝐏𝐥𝐚𝐭𝐟𝐨𝐫𝐦")
        except Exception as e:
            logger.error(f"Error: {e}")
            await m.answer(f"❌ 𝐄𝐫𝐫𝐨𝐫\n{str(e)[:100]}")

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

async def main():
    logger.info("NAGU DOWNLOADER BOT - STARTING")
    logger.info(f"Semaphore: 16 concurrent downloads")
    logger.info(f"Proxies: {len(PROXIES)}")
    
    # Check cookie folders
    if os.path.exists(YT_COOKIES_FOLDER):
        yt_cookies = len(glob.glob(f"{YT_COOKIES_FOLDER}/*.txt"))
        logger.info(f"YT cookies: {yt_cookies} files")
    
    if os.path.exists(YT_MUSIC_COOKIES_FOLDER):
        music_cookies = len(glob.glob(f"{YT_MUSIC_COOKIES_FOLDER}/*.txt"))
        logger.info(f"YT Music cookies: {music_cookies} files")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
