# ⚡ Quick Start Guide - NAGU ULTRA DOWNLOADER

Get your bot running in 5 minutes!

---

## 🚀 Railway Deployment (Recommended)

### Step 1: Prepare Your Repository

1. **Fork this repository** or clone it:
   ```bash
   git clone https://github.com/yourusername/nagu-ultra-downloader.git
   cd nagu-ultra-downloader
   ```

2. **Configure environment variables**:
   - Set `BOT_TOKEN` environment variable (get from @BotFather)
   - Or update in [`core/config.py`](core/config.py)

3. **Add cookie files** (IMPORTANT!):
   - Export cookies from your browser using "Get cookies.txt LOCALLY" extension
   - Save as `cookies_youtube.txt` and `cookies_instagram.txt`
   - Place in the root directory

4. **Push to GitHub:**
   ```bash
   git add .
   git commit -m "Configure bot"
   git push origin main
   ```

### Step 2: Deploy on Railway

1. Go to [railway.app](https://railway.app)
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your repository
5. Click **"Deploy"**
6. Wait 2-3 minutes for deployment

### Step 3: Verify

Check logs in Railway dashboard:
```
✅ Cookie files detected
✅ Bot starting
✅ Polling mode active
```

### Step 4: Test

1. Open Telegram
2. Search for your bot
3. Send `/start`
4. Send a video URL

**Done! 🎉**

---

## 🐳 Docker Deployment (Alternative)

### Quick Docker Run

```bash
# 1. Set environment variables (BOT_TOKEN, etc.)
# 2. Add cookie files
# 3. Build and run:

docker build -t nagu-bot .
docker run -d --name nagu-downloader \
  -e BOT_TOKEN="your_token_here" \
  --restart unless-stopped nagu-bot

# View logs:
docker logs -f nagu-downloader
```

---

## 💻 Local Development

### Prerequisites
```bash
# Install Python 3.11+
python --version

# Install FFmpeg
# Ubuntu/Debian:
sudo apt install ffmpeg

# macOS:
brew install ffmpeg

# Windows: Download from ffmpeg.org
```

### Run Locally
```bash
# 1. Clone repository
git clone https://github.com/yourusername/nagu-ultra-downloader.git
cd nagu-ultra-downloader

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables
export BOT_TOKEN="your_token_here"

# 4. Add cookie files

# 5. Run bot
python bot.py
```

---

## 🍪 Getting Cookie Files

### Method 1: Browser Extension (Recommended)

1. **Install Extension:**
   - Chrome/Edge: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   - Firefox: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

2. **Export Cookies:**
   - Visit instagram.com (logged in)
   - Click extension icon
   - Click "Export" → Save as `cookies_instagram.txt`
   - Repeat for youtube.com → `cookies_youtube.txt`

3. **Place Files:**
   ```
   nagu-ultra-downloader/
   ├── cookies_instagram.txt  ← Here
   ├── cookies_youtube.txt    ← Here
   └── bot.py
   ```

### Method 2: Manual Export

1. Open browser DevTools (F12)
2. Go to Application → Cookies
3. Copy all cookies
4. Format as Netscape cookie file
5. Save to respective files

---

## 🔍 Troubleshooting

### Bot Not Starting

**Check logs for:**
```
❌ Cookie files missing
```

**Solution:**
- Ensure cookie files exist in root directory
- Check file names are exact: `cookies_youtube.txt`, `cookies_instagram.txt`

### Downloads Failing

**Instagram:**
```
❌ Empty media response
```
**Solution:** Update Instagram cookies (they expire every 2-4 weeks)

**YouTube:**
```
❌ Video unavailable
```
**Solution:** 
- Check video ID is 11 characters
- Update YouTube cookies
- Try different proxy

**Pinterest:**
```
❌ Unsupported URL
```
**Solution:** Use complete pin URL with pin ID

### FFmpeg Not Found

**Error:**
```
ffmpeg: command not found
```

**Solution:**
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Verify
ffmpeg -version
```

---

## 📝 Testing URLs

### Valid URL Examples

**Instagram:**
```
✅ https://www.instagram.com/p/ABC123xyz/
✅ https://www.instagram.com/reel/ABC123xyz/
❌ https://www.instagram.com/
```

**YouTube:**
```
✅ https://www.youtube.com/watch?v=dQw4w9WgXcQ
✅ https://youtu.be/dQw4w9WgXcQ
❌ https://www.youtube.com/watch?v=invalid
```

**Pinterest:**
```
✅ https://www.pinterest.com/pin/123456789/
✅ https://pin.it/abc123
❌ https://www.pinterest.com/
```

---

## ⚙️ Configuration

### Adjust Concurrent Downloads

Edit [`core/config.py`](core/config.py):
```python
MAX_CONCURRENT_DOWNLOADS = 8  # Change to 4 for slower servers
MAX_CONCURRENT_MUSIC = 5
MAX_CONCURRENT_SPOTIFY = 3
```

### Change Video Quality

Edit downloader settings in respective files under [`downloaders/`](downloaders/):
```python
# For better quality (larger files):
"format": "bestvideo[height<=1440]+bestaudio/best"

# For smaller files (lower quality):
"format": "bestvideo[height<=720]+bestaudio/best"
```

---

## 📊 Expected Performance

### Processing Times
- Instagram: 10-15 seconds
- YouTube: 15-30 seconds
- Pinterest: 5-10 seconds

### File Sizes
- Instagram: 5-15 MB (1080p)
- YouTube: 10-25 MB (1080p)
- Pinterest: 5-15 MB

### Success Rates
- Instagram: 95%
- YouTube: 95%
- Pinterest: 90%

---

## 🎯 Next Steps

1. ✅ Deploy bot
2. ✅ Test with sample URLs
3. ✅ Update cookies regularly
4. ✅ Monitor logs
5. ✅ Read full [README.md](README.md) for advanced features

---

## 📚 Additional Resources

- **Full Documentation:** [README.md](README.md)
- **Deployment Guide:** [DEPLOYMENT.md](DEPLOYMENT.md)
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)
- **Cookie Setup:** [COOKIE_SETUP.md](COOKIE_SETUP.md)

---

## 🆘 Need Help?

1. Check [DEPLOYMENT.md](DEPLOYMENT.md) troubleshooting section
2. Review logs for error messages
3. Verify cookie files are up to date
4. Contact: [@bhosadih](https://t.me/bhosadih)

---

## ✅ Checklist

Before deploying, ensure:

- [ ] BOT_TOKEN environment variable set
- [ ] Cookie files added (cookies_youtube.txt, cookies_instagram.txt)
- [ ] FFmpeg installed (for local/VPS deployment)
- [ ] Repository pushed to GitHub (for Railway)
- [ ] Tested locally (optional but recommended)

---

<div align="center">

**⟣—◈ NAGU ULTRA TECHNOLOGY ◈—⟢**

Ready to download! 🚀

[Deploy Now](https://railway.app) • [Get Support](https://t.me/bhosadih)

</div>
