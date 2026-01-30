# Bot Credentials & Deployment Guide

## All Credentials Extracted from Code

### Bot Token
```
BOT_TOKEN=8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640
```

### Spotify API
```
SPOTIFY_CLIENT_ID=3d5660b77d6a4aba827c3865c6397a22
SPOTIFY_CLIENT_SECRET=cd2b556d3e2f42598874ccca1d6e310b
```

### Redis Database (Upstash)
```
REDIS_URL=https://together-snail-28026.upstash.io
REDIS_TOKEN=AW16AAIncDExZmI3ZWM3YzUwMjA0MzIxOWJmOTQxY2VkMDQzNDdhZnAxMjgwMjY
```

### Proxies (6 proxies)
```
PROXIES=http://203033:JmNd95Z3vcX@196.51.85.7:8800,http://203033:JmNd95Z3vcX@196.51.218.227:8800,http://203033:JmNd95Z3vcX@196.51.106.149:8800,http://203033:JmNd95Z3vcX@170.130.62.211:8800,http://203033:JmNd95Z3vcX@196.51.106.30:8800,http://203033:JmNd95Z3vcX@196.51.85.207:8800
```

### Sticker IDs (Optional)
```
IG_STICKER=CAACAgIAAxkBAAEadEdpekZa1-2qYm-1a3dX0JmM_Z9uDgAC4wwAAjAT0Euml6TE9QhYWzgE
YT_STICKER=CAACAgIAAxkBAAEaedlpez9LOhwF-tARQsD1V9jzU8iw1gACQjcAAgQyMEixyZ896jTkCDgE
PIN_STICKER=CAACAgIAAxkBAAEaegZpe0KJMDIkiCbudZrXhJDwBXYHqgACExIAAq3mUUhZ4G5Cm78l2DgE
MUSIC_STICKER=CAACAgIAAxkBAAEaegZpe0KJMDIkiCbudZrXhJDwBXYHqgACExIAAq3mUUhZ4G5Cm78l2DgE
```

## Quick Deployment on VPS

### Method 1: Using .env file (Recommended)
1. Copy the `.env` file to your VPS
2. Make sure it's in the same directory as `main.py`
3. Run: `python main.py`

### Method 2: Export as Environment Variables
```bash
export BOT_TOKEN="8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"
export SPOTIFY_CLIENT_ID="3d5660b77d6a4aba827c3865c6397a22"
export SPOTIFY_CLIENT_SECRET="cd2b556d3e2f42598874ccca1d6e310b"
export REDIS_URL="https://together-snail-28026.upstash.io"
export REDIS_TOKEN="AW16AAIncDExZmI3ZWM3YzUwMjA0MzIxOWJmOTQxY2VkMDQzNDdhZnAxMjgwMjY"
export PROXIES="http://203033:JmNd95Z3vcX@196.51.85.7:8800,http://203033:JmNd95Z3vcX@196.51.218.227:8800,http://203033:JmNd95Z3vcX@196.51.106.149:8800,http://203033:JmNd95Z3vcX@170.130.62.211:8800,http://203033:JmNd95Z3vcX@196.51.106.30:8800,http://203033:JmNd95Z3vcX@196.51.85.207:8800"
```

### Method 3: Using systemd service
Create `/etc/systemd/system/nagu-bot.service`:
```ini
[Unit]
Description=NAGU Downloader Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/bot
Environment="BOT_TOKEN=8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"
Environment="SPOTIFY_CLIENT_ID=3d5660b77d6a4aba827c3865c6397a22"
Environment="SPOTIFY_CLIENT_SECRET=cd2b556d3e2f42598874ccca1d6e310b"
Environment="REDIS_URL=https://together-snail-28026.upstash.io"
Environment="REDIS_TOKEN=AW16AAIncDExZmI3ZWM3YzUwMjA0MzIxOWJmOTQxY2VkMDQzNDdhZnAxMjgwMjY"
Environment="PROXIES=http://203033:JmNd95Z3vcX@196.51.85.7:8800,http://203033:JmNd95Z3vcX@196.51.218.227:8800,http://203033:JmNd95Z3vcX@196.51.106.149:8800,http://203033:JmNd95Z3vcX@170.130.62.211:8800,http://203033:JmNd95Z3vcX@196.51.106.30:8800,http://203033:JmNd95Z3vcX@196.51.85.207:8800"
ExecStart=/usr/bin/python3 main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable nagu-bot
sudo systemctl start nagu-bot
```

## Docker Deployment

The bot already has a Dockerfile. Build and run:
```bash
docker build -t nagu-bot .
docker run -d \
  -e BOT_TOKEN="8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640" \
  -e SPOTIFY_CLIENT_ID="3d5660b77d6a4aba827c3865c6397a22" \
  -e SPOTIFY_CLIENT_SECRET="cd2b556d3e2f42598874ccca1d6e310b" \
  -e REDIS_URL="https://together-snail-28026.upstash.io" \
  -e REDIS_TOKEN="AW16AAIncDExZmI3ZWM3YzUwMjA0MzIxOWJmOTQxY2VkMDQzNDdhZnAxMjgwMjY" \
  -e PROXIES="http://203033:JmNd95Z3vcX@196.51.85.7:8800,http://203033:JmNd95Z3vcX@196.51.218.227:8800,http://203033:JmNd95Z3vcX@196.51.106.149:8800,http://203033:JmNd95Z3vcX@170.130.62.211:8800,http://203033:JmNd95Z3vcX@196.51.106.30:8800,http://203033:JmNd95Z3vcX@196.51.85.207:8800" \
  --name nagu-bot \
  nagu-bot
```

## Important Notes

1. **Security**: The `.env` file is in `.gitignore` and won't be committed to Git
2. **Redis**: Free tier is sufficient for management features
3. **Proxies**: All 6 proxies are included and will be rotated automatically
4. **Picture**: Add your custom image to `assets/picture.png` for premium start message

## Testing

After deployment, test with:
- `/start` - Should show welcome message (with image if added)
- `/help` - Should show all commands
- Send any Instagram/YouTube/Spotify link
- Try management commands in a group

## Troubleshooting

If bot doesn't start:
1. Check if all environment variables are set: `env | grep BOT_TOKEN`
2. Check Redis connection: `curl https://together-snail-28026.upstash.io`
3. Check logs: `tail -f /var/log/nagu-bot.log`
4. Verify Python dependencies: `pip install -r requirements.txt`
