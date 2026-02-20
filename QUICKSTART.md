# Quick Start — Nagu Downloader Bot

Get your bot running in minutes.

---

## Prerequisites

- Python 3.10+
- FFmpeg installed (`ffmpeg -version` to verify)
- Redis instance (Upstash free tier works)
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Spotify API credentials (from [developer.spotify.com](https://developer.spotify.com))

---

## 1. Clone & Install

```bash
git clone https://github.com/ULTRABE/nagudownloaderbot.git
cd nagudownloaderbot
pip install -r requirements.txt
```

---

## 2. Configure Environment Variables

Create a `.env` file or set environment variables in your deployment platform:

```env
# Required
BOT_TOKEN=your_telegram_bot_token

# Spotify (https://developer.spotify.com/dashboard)
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret

# Redis (Upstash: https://upstash.com)
REDIS_URL=https://your-redis.upstash.io
REDIS_TOKEN=your_redis_token

# Admin IDs — comma-separated Telegram user IDs
ADMIN_IDS=123456789

# Optional
PROXIES=http://proxy1:port,http://proxy2:port
```

---

## 3. Add Cookie Files (Recommended)

Cookie files improve download reliability and bypass rate limits.

**Export cookies** using the [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) browser extension.

Place files here:
```
yt cookies/
  ├── cookie1.txt
  └── cookie2.txt

yt music cookies/
  ├── music_cookie1.txt
  └── music_cookie2.txt

cookies_instagram.txt   (optional)
```

---

## 4. Add Welcome Image (Optional)

Place a `picture.png` in the `assets/` folder. It will be sent with `/start`.

---

## 5. Run

```bash
python bot.py
```

Expected startup output:
```
✓ Configuration validated
✓ ffmpeg available
✓ ffprobe available
✓ All handlers registered
Bot started
```

---

## Docker

```bash
docker build -t nagu-bot .
docker run -d --env-file .env nagu-bot
```

---

## Railway Deployment

1. Fork this repository
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add environment variables in the Railway dashboard
4. Deploy

---

## Testing

Send these to your bot to verify everything works:

| Test | Expected |
|------|----------|
| `/start` | Welcome message with image |
| `/ping` | Pong with latency |
| `/help` | Feature list |
| YouTube Short URL | Video delivered |
| Spotify track URL | Audio delivered |
| Instagram reel URL | Video delivered |
| Pinterest pin URL | Video delivered |

---

## Admin Setup

1. Set your Telegram user ID in `ADMIN_IDS` env var
2. Use `/assign` to configure custom emojis for UI positions
3. Use `/broadcast` to send messages to all users and groups
4. Use `/stats` to see user/group counts

---

## Troubleshooting

**Bot not starting**
- Check `BOT_TOKEN` is valid
- Verify Redis connection (`REDIS_URL` + `REDIS_TOKEN`)

**Downloads failing**
- Run `ffmpeg -version` — must be installed
- Update yt-dlp: `pip install -U yt-dlp`
- Refresh cookie files (they expire every 2–4 weeks)

**Spotify not working**
- Verify `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`
- Install spotdl: `pip install spotdl`

**Admin commands not working**
- Verify your user ID is in `ADMIN_IDS`
- Use `/id` to get your Telegram user ID

---

## Additional Resources

- [README.md](README.md) — Full documentation
- [DEPLOYMENT.md](DEPLOYMENT.md) — Deployment guide
- [COOKIE_SETUP.md](COOKIE_SETUP.md) — Cookie setup guide
- [CHANGELOG.md](CHANGELOG.md) — Version history
