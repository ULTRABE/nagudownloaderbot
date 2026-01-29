# ⟣—◈ NAGU ULTRA DOWNLOADER ◈—⟢

<div align="center">

![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-green.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)
![Status](https://img.shields.io/badge/status-active-success.svg)

**🚀 Lightning Fast Video Downloader Bot for Telegram**

*Download videos from Instagram, YouTube, and Pinterest with Ultra HD quality and optimized file sizes*

[Features](#-features) • [Installation](#-installation) • [Usage](#-usage) • [Configuration](#-configuration) • [Deployment](#-deployment)

</div>

---

## ✨ Features

### 🎯 **Multi-Platform Support**
- 📸 **Instagram**: Posts, Reels, IGTV, Stories
- 🎬 **YouTube**: Videos, Shorts, Live Streams
- 📌 **Pinterest**: Video Pins, Idea Pins

### ⚡ **Performance**
- 🚀 Lightning-fast concurrent downloads (8 simultaneous)
- 💾 Smart compression with VP9 codec
- 🔄 Automatic proxy rotation for reliability
- ⚙️ Multi-threaded FFmpeg processing

### 🎨 **Premium UI/UX**
- 💎 Beautiful formatted messages with Unicode symbols
- 📊 Real-time progress indicators
- ⏱️ Response time tracking
- 🎭 Platform-specific animated stickers

### 🔒 **Security & Privacy**
- 🔐 Cookie-based authentication
- 🌐 Proxy support for anonymity
- 🔄 User-Agent rotation
- 📝 Comprehensive error logging

### 🎥 **Quality Options**
- 📺 Ultra HD support (up to 1080p)
- 💾 Optimized file sizes (VP9 + Opus)
- 🎬 Streaming-optimized output
- 🔊 High-quality audio (96kbps Opus)

---

## 📋 Requirements

- Python 3.11+
- FFmpeg with VP9 and Opus support
- Telegram Bot Token
- Cookie files for authentication

---

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/nagu-ultra-downloader.git
cd nagu-ultra-downloader
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Install FFmpeg

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html)

### 4. Configure Bot Token

Edit [`main.py`](main.py:12) and replace with your bot token:

```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
```

### 5. Add Cookie Files

Create cookie files for authentication:

- `cookies_youtube.txt` - YouTube cookies
- `cookies_instagram.txt` - Instagram cookies

**How to export cookies:**
1. Install browser extension: "Get cookies.txt LOCALLY"
2. Visit the platform while logged in
3. Export cookies in Netscape format
4. Save to the respective file

---

## 💻 Usage

### Start the Bot

```bash
python main.py
```

### Using the Bot

1. Start a chat with your bot on Telegram
2. Send `/start` to see the welcome message
3. Send any supported video URL
4. Wait for processing (5-30 seconds)
5. Receive your video!

### Supported URL Formats

**Instagram:**
```
https://www.instagram.com/p/ABC123xyz/
https://www.instagram.com/reel/ABC123xyz/
```

**YouTube:**
```
https://www.youtube.com/watch?v=dQw4w9WgXcQ
https://youtu.be/dQw4w9WgXcQ
```

**Pinterest:**
```
https://www.pinterest.com/pin/123456789/
https://pin.it/abc123
```

---

## ⚙️ Configuration

### Video Quality Settings

**Instagram** ([`main.py`](main.py:136)):
```python
"format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best"
```

**YouTube** ([`main.py`](main.py:413)):
```python
"format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best"
```

### Compression Settings

**VP9 Encoding** ([`main.py`](main.py:485)):
```python
"-c:v", "libvpx-vp9", "-crf", "31", "-b:v", "0",
"-cpu-used", "5", "-row-mt", "1", "-threads", "4",
"-c:a", "libopus", "-b:a", "96k"
```

### Concurrent Downloads

Adjust semaphore limit ([`main.py`](main.py:58)):
```python
semaphore = asyncio.Semaphore(8)  # 8 concurrent downloads
```

### Proxy Configuration

Add/modify proxies ([`main.py`](main.py:30)):
```python
PROXIES = [
    "http://user:pass@ip:port",
    # Add more proxies
]
```

---

## 🌐 Deployment

### Railway

1. Create a new project on [Railway](https://railway.app)
2. Connect your GitHub repository
3. Add environment variables (if needed)
4. Deploy!

**Procfile:**
```
web: python main.py
```

### Docker

**Build:**
```bash
docker build -t nagu-downloader .
```

**Run:**
```bash
docker run -d --name nagu-bot nagu-downloader
```

### Heroku

```bash
heroku create your-app-name
git push heroku main
heroku ps:scale web=1
```

---

## 🐛 Troubleshooting

### Common Issues

**1. Instagram: "Empty media response"**
- ✅ Update cookies from a logged-in session
- ✅ Check if the post is public
- ✅ Verify URL format is correct

**2. YouTube: "Video unavailable"**
- ✅ Check if video ID is valid (11 characters)
- ✅ Update cookies for age-restricted content
- ✅ Try different proxy

**3. Pinterest: "Unsupported URL"**
- ✅ Ensure URL contains pin ID
- ✅ Use complete URL, not base domain
- ✅ Check if pin contains video content

### Enable Debug Logging

Modify logging level ([`main.py`](main.py:14)):
```python
logging.basicConfig(level=logging.DEBUG)
```

---

## 📊 Performance Optimization

### File Size Reduction

| Platform | Original | Optimized | Reduction |
|----------|----------|-----------|-----------|
| Instagram | 25 MB | 8 MB | 68% |
| YouTube | 50 MB | 15 MB | 70% |
| Pinterest | 10 MB | 10 MB | 0% (copy) |

### Processing Speed

- **Instagram**: 5-15 seconds
- **YouTube**: 10-30 seconds
- **Pinterest**: 3-10 seconds

*Times vary based on video length and server load*

---

## 🔧 Advanced Configuration

### Custom FFmpeg Parameters

**For better quality** (larger files):
```python
"-crf", "28"  # Lower CRF = better quality
"-b:a", "128k"  # Higher audio bitrate
```

**For smaller files** (lower quality):
```python
"-crf", "35"  # Higher CRF = smaller files
"-b:a", "48k"  # Lower audio bitrate
```

### Cookie Auto-Refresh

Consider implementing automatic cookie refresh:
```python
# Check cookie expiration
# Re-authenticate if needed
# Update cookie files
```

---

## 📝 API Reference

### Main Functions

#### `validate_instagram_url(url)`
Validates Instagram URL format
- **Returns**: `bool`

#### `validate_youtube_url(url)`
Validates YouTube URL format
- **Returns**: `bool`

#### `validate_pinterest_url(url)`
Validates Pinterest URL format
- **Returns**: `bool`

#### `handle_instagram(m, url)`
Downloads and processes Instagram videos
- **Parameters**: 
  - `m`: Message object
  - `url`: Instagram URL

#### `handle_youtube(m, url)`
Downloads and processes YouTube videos
- **Parameters**:
  - `m`: Message object
  - `url`: YouTube URL

#### `handle_pinterest(m, url)`
Downloads and processes Pinterest videos
- **Parameters**:
  - `m`: Message object
  - `url`: Pinterest URL

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 👨‍💻 Author

**NAGU ULTRA TECHNOLOGY**

- Telegram: [@bhosadih](https://t.me/bhosadih)
- Bot: [@nagudownloaderbot](https://t.me/nagudownloaderbot)

---

## 🙏 Acknowledgments

- [aiogram](https://github.com/aiogram/aiogram) - Telegram Bot framework
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Video downloader
- [FFmpeg](https://ffmpeg.org/) - Video processing

---

## ⚠️ Disclaimer

This bot is for educational purposes only. Users are responsible for complying with the terms of service of Instagram, YouTube, and Pinterest. The developers are not responsible for any misuse of this software.

---

<div align="center">

**⟣—◈ Made with ❤️ by NAGU ULTRA ◈—⟢**

⭐ Star this repo if you find it useful!

</div>
