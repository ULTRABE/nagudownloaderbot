# NAGU Downloader Bot

**Production-grade Telegram bot for downloading media from multiple platforms with advanced management features.**

## 🚀 Features

### Media Download
- **Instagram** — Posts, Reels, Stories
- **YouTube** — Videos, Shorts, Streams (with cookie rotation)
- **Pinterest** — Video Pins (with URL resolution)
- **Spotify** — Full playlist downloads with real-time progress
- **MP3 Search** — Search and download music with metadata

### Admin & Moderation
- **User Management** — Promote/demote admins
- **Moderation Tools** — Mute, unmute, ban, unban
- **Permission System** — Proper admin detection with caching
- **Content Filtering** — Word filters and exact blocklists

### Premium Features
- **Real-time Progress** — Live progress bars for Spotify downloads
- **Batch Delivery** — Songs sent in batches of 10 to user DM
- **Whisper Command** — Private messages in groups
- **Premium UI** — Clean quoted blocks throughout
- **Clickable Mentions** — All user references are clickable

### Performance
- **Fully Async** — Non-blocking architecture
- **Worker Pools** — Concurrent download management
- **Cookie Rotation** — Multiple cookies for reliability
- **Proxy Support** — Configurable proxy rotation
- **Rate Limiting** — Semaphore-based concurrency control

## 📋 Requirements

- Python 3.10+
- Redis (Upstash or local)
- FFmpeg (for audio processing)
- spotdl (for Spotify downloads)
- yt-dlp (for video downloads)

## 🔧 Installation

### 1. Clone Repository
```bash
git clone <repository-url>
cd nagu-downloader-bot
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Install System Dependencies
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
```

### 4. Configure Environment Variables

Create a `.env` file:

```env
# Bot Configuration
BOT_TOKEN=your_telegram_bot_token

# Spotify API (get from https://developer.spotify.com)
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret

# Redis (Upstash or local)
REDIS_URL=your_redis_url
REDIS_TOKEN=your_redis_token

# Optional: Proxies (comma-separated)
PROXIES=http://proxy1:port,http://proxy2:port

# Optional: Custom Stickers
IG_STICKER=sticker_file_id
YT_STICKER=sticker_file_id
PIN_STICKER=sticker_file_id
MUSIC_STICKER=sticker_file_id
```

### 5. Add Cookies (Optional but Recommended)

For better reliability, add cookie files:

```
yt cookies/
  ├── cookie1.txt
  ├── cookie2.txt
  └── cookie3.txt

yt music cookies/
  ├── music_cookie1.txt
  └── music_cookie2.txt

cookies_instagram.txt (optional)
```

### 6. Add Start Image (Optional)

Place a `picture.png` in the `assets/` folder for the `/start` command.

## 🚀 Running the Bot

### Development
```bash
python bot.py
```

### Production (with Docker)
```bash
docker build -t nagu-bot .
docker run -d --env-file .env nagu-bot
```

### Production (with systemd)
```bash
sudo cp nagu-bot.service /etc/systemd/system/
sudo systemctl enable nagu-bot
sudo systemctl start nagu-bot
```

## 📖 Usage

### Basic Commands

#### Download Commands
- Send any Instagram/YouTube/Pinterest/Spotify link
- `/mp3 <song name>` — Search and download music

#### Info Commands
- `/start` — Welcome message with user info
- `/help` — View all features (5 premium panels)
- `/id` — Get user ID
- `/chatid` — Get chat ID
- `/myinfo` — Get detailed user information

#### Admin Commands (Groups Only)
- `/promote` — Promote user to admin (reply to user)
- `/demote` — Demote admin (reply to user)
- `/mute [minutes]` — Mute user (reply to user)
- `/unmute` — Unmute user (reply to user)
- `/ban` — Ban user (reply to user)
- `/unban` — Unban user (reply to user)

#### Filter Commands (Groups Only)
- `/filter <word>` — Add word to filter (substring match)
- `/unfilter <word>` — Remove word from filter
- `/filters` — List all filters
- `/block <word>` — Block exact word
- `/unblock <word>` — Unblock word
- `/blocklist` — List all blocked words

#### Other Commands
- `/whisper <message>` — Send private message (reply to user in group)

### Spotify Workflow

1. User sends Spotify playlist link
2. Bot deletes user message after 3-5 seconds
3. Bot sends "Spotify Playlist Fetched" message
4. Live progress updates with dual progress bars:
   - Main bar: Overall playlist progress
   - Sub bar: Current song progress
5. Songs sent in batches of 10 to user's DM
6. Final completion message in group

## 🏗️ Architecture

```
/core           → Bot initialization, config, dispatcher
/downloaders    → Instagram, Pinterest, YouTube, Spotify, MP3
/workers        → Async queues, concurrency pools
/ui             → Message formatting, progress bars
/admin          → Permissions, moderation, filters
/utils          → Logging, Redis, helpers
/assets         → Images for UI
```

## ⚡ Performance Optimizations

- **Async Subprocess** — All downloads run asynchronously
- **Worker Pools** — Configurable concurrency limits
- **Cookie Rotation** — Random cookie selection per request
- **Proxy Rotation** — Random proxy selection per request
- **Redis Caching** — Admin permissions cached for 5 minutes
- **Batch Processing** — Spotify songs sent in batches
- **Rate Limiting** — Semaphore-based concurrency control

## 🔒 Security

- All secrets stored in environment variables
- Admin permissions verified with Telegram API
- Redis-backed permission caching
- Secure whisper delivery (no public leaks)
- Input validation and sanitization

## 🐛 Troubleshooting

### Bot not responding
- Check bot token is correct
- Verify Redis connection
- Check logs for errors

### Downloads failing
- Verify FFmpeg is installed
- Check cookie files are valid
- Try adding proxies
- Check yt-dlp is up to date

### Spotify not working
- Verify Spotify API credentials
- Check spotdl is installed
- Ensure FFmpeg is available

### Admin commands not working
- Verify user is Telegram admin
- Check Redis connection
- Clear admin cache if needed

## 📝 License

MIT License - See LICENSE file for details

## 👥 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📧 Support

For issues and questions:
- Open an issue on GitHub
- Contact: @bhosadih

## 🎯 Roadmap

- [ ] Twitter/X downloader
- [ ] TikTok downloader
- [ ] Batch download queue
- [ ] User statistics
- [ ] Download history
- [ ] Custom download quality settings
- [ ] Multi-language support

---

**Built with ❤️ for the Telegram community**
