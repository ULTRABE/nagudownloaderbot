# Nagu Downloader Bot

**A production-grade Telegram bot for downloading media from YouTube, Instagram, Spotify, and Pinterest — with premium emoji support, download logging, and admin tools.**

---

## Features

### Media Download
- **YouTube** — Videos, Shorts, YouTube Music (320kbps), Playlists (audio & video)
- **Instagram** — Posts, Reels, Stories
- **Spotify** — Single tracks and full playlists (streamed track-by-track to DM)
- **Pinterest** — Video pins and carousels
- **MP3 Extraction** — Extract audio from any replied video via `/mp3`

### UI & Emoji System
- **Dynamic Emoji Resolver** — All emojis loaded from Redis at runtime via `get_emoji_async()`
- **Admin Emoji Assignment** — `/assign` command lets admins set custom Telegram premium emojis or unicode emojis for any UI position
- **Fallback System** — Always falls back to `DEFAULT_EMOJIS` if Redis is unavailable — never crashes
- **HTML Parse Mode** — All messages use `parse_mode="HTML"` for proper `<tg-emoji>` rendering

### Download Log Channel
- Every download is logged to a private Telegram channel
- Clickable user mention (`tg://user?id=...`)
- Clickable group link for public groups; plain title for private groups
- Shows: user, link, chat, media type, time taken

### Admin Tools
- `/broadcast` — Send text or media to all users and groups
- `/assign` — Configure custom emojis for each UI position
- `/stats` — User and group counts
- `/admin` — Admin panel
- `/ping` — Health check with latency

### Performance
- **Fully Async** — Non-blocking architecture with aiogram 3.x
- **Semaphore-based Concurrency** — Configurable per-platform limits
- **URL Cache** — Telegram `file_id` caching via Redis (instant re-sends)
- **Cookie Rotation** — Multiple cookie files per platform
- **Proxy Support** — Configurable proxy rotation
- **Per-User Slot Limiting** — Prevents abuse via watchdog

---

## Requirements

- Python 3.10+
- Redis (Upstash or local)
- FFmpeg + FFprobe
- spotdl (for Spotify downloads)
- yt-dlp (for YouTube/Instagram/Pinterest)

---

## Environment Variables

```env
# Required
BOT_TOKEN=your_telegram_bot_token

# Spotify API (https://developer.spotify.com)
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret

# Redis
REDIS_URL=your_redis_url
REDIS_TOKEN=your_redis_token

# Admin IDs (comma-separated Telegram user IDs)
ADMIN_IDS=123456789,987654321

# Optional
PROXIES=http://proxy1:port,http://proxy2:port
MAX_CONCURRENT_DOWNLOADS=8
MAX_CONCURRENT_MUSIC=5
MAX_CONCURRENT_SPOTIFY=3
MAX_CONCURRENT_PER_USER=2
DOWNLOAD_TIMEOUT=120
```

---

## Cookie Files

Place cookie files in the following locations for better reliability:

```
yt cookies/
  ├── cookie1.txt
  └── cookie2.txt

yt music cookies/
  ├── music_cookie1.txt
  └── music_cookie2.txt

cookies_instagram.txt   (optional)
```

Export cookies using the "Get cookies.txt LOCALLY" browser extension.

---

## Installation

```bash
# 1. Clone
git clone https://github.com/ULTRABE/nagudownloaderbot.git
cd nagudownloaderbot

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install FFmpeg
# Ubuntu/Debian:
sudo apt install ffmpeg
# macOS:
brew install ffmpeg

# 4. Configure environment variables (see above)

# 5. Run
python bot.py
```

---

## Docker

```bash
docker build -t nagu-bot .
docker run -d --env-file .env nagu-bot
```

---

## Commands

### User Commands
| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Show all features |
| `/id` | Get your Telegram user ID |
| `/chatid` | Get current chat ID |
| `/myinfo` | Account details |
| `/mp3` | Extract audio from replied video |
| `/ping` | Health check |

### Admin Commands
| Command | Description |
|---------|-------------|
| `/broadcast <text>` | Broadcast text to all users & groups |
| `/broadcast` (reply) | Broadcast any media message |
| `/assign` | Configure custom emojis for UI positions |
| `/stats` | User and group statistics |
| `/admin` | Admin panel |

---

## Architecture

```
bot.py                  — Entry point, startup checks
core/
  bot.py                — Bot + dispatcher initialization
  config.py             — Centralized config (env vars)
  emoji_config.py       — Legacy emoji config (core layer)
downloaders/
  router.py             — URL routing, admin commands, info commands
  youtube.py            — YouTube video/audio/shorts/playlist
  instagram.py          — Instagram posts/reels
  spotify.py            — Spotify tracks and playlists
  pinterest.py          — Pinterest video pins
ui/
  emoji_config.py       — Async emoji resolver (get_emoji_async)
  formatting.py         — All user-facing message formatters (async)
  stickers.py           — Platform sticker sending
  progress.py           — Progress bar helpers
utils/
  log_channel.py        — Download activity logger
  broadcast.py          — Mass messaging engine
  cache.py              — URL → file_id Redis cache
  error_handler.py      — Async error message formatter
  helpers.py            — Cookie/proxy/metadata helpers
  media_processor.py    — FFmpeg encode/split/info
  rate_limiter.py       — Per-user rate limiting
  redis_client.py       — Redis connection
  user_state.py         — User registration/cooldown state
  watchdog.py           — Per-user concurrent slot control
workers/
  task_queue.py         — Semaphores for concurrency control
assets/
  picture.png           — Welcome image (optional)
```

---

## Emoji System

Admins can assign custom Telegram premium emojis (or plain unicode) to any UI position using `/assign`.

Emojis are stored in Redis under `emoji:{KEY}` and resolved at runtime:
- **Numeric ID** → rendered as `<tg-emoji emoji-id="...">fallback</tg-emoji>`
- **Unicode string** → returned as-is
- **Not set / Redis unavailable** → falls back to `DEFAULT_EMOJIS` dict

Available keys: `SUCCESS`, `ERROR`, `PROCESS`, `MUSIC`, `VIDEO`, `PLAYLIST`, `SPOTIFY`, `YT`, `INSTA`, `PINTEREST`, `DOWNLOAD`, `COMPLETE`, `BROADCAST`, `INFO`, `ID`, `USER`, `PING`, `STAR`, `FIRE`, `ROCKET`, `CROWN`, `DIAMOND`, `ZAP`, `WAVE`, `DELIVERED`, `FAST`, `LOADING`, `CHECK`

---

## Troubleshooting

**Bot not responding**
- Check `BOT_TOKEN` is correct
- Verify Redis connection (`REDIS_URL` / `REDIS_TOKEN`)
- Check logs for errors

**Downloads failing**
- Verify FFmpeg is installed (`ffmpeg -version`)
- Check cookie files are valid and not expired
- Update yt-dlp: `pip install -U yt-dlp`

**Spotify not working**
- Verify `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`
- Check spotdl is installed: `pip install spotdl`
- Ensure FFmpeg is available

**Admin commands not working**
- Verify your Telegram user ID is in `ADMIN_IDS` env var

---

## License

MIT License

---

**Built for the Telegram community**
