# 🚀 Deployment Guide - NAGU ULTRA DOWNLOADER

This guide covers deploying your bot to various platforms.

---

## 📋 Table of Contents

1. [Railway Deployment](#railway-deployment)
2. [Heroku Deployment](#heroku-deployment)
3. [Docker Deployment](#docker-deployment)
4. [VPS Deployment](#vps-deployment)
5. [Troubleshooting](#troubleshooting)

---

## 🚂 Railway Deployment

Railway is the recommended platform for deployment.

### Prerequisites
- GitHub account
- Railway account ([railway.app](https://railway.app))
- Bot token from [@BotFather](https://t.me/BotFather)

### Steps

1. **Fork/Clone Repository**
   ```bash
   git clone https://github.com/yourusername/nagu-ultra-downloader.git
   cd nagu-ultra-downloader
   ```

2. **Set Environment Variables**
   
   ```bash
   export BOT_TOKEN="YOUR_BOT_TOKEN_HERE"
   # Or add to .env file or Railway environment variables
   ```

3. **Add Cookie Files**
   
   Place your cookie files in the root directory:
   - `cookies_youtube.txt`
   - `cookies_instagram.txt`
   - `cookies_music.txt` (optional)

4. **Push to GitHub**
   ```bash
   git add .
   git commit -m "Configure bot for deployment"
   git push origin main
   ```

5. **Deploy on Railway**
   - Go to [railway.app](https://railway.app)
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository
   - Railway will auto-detect the Dockerfile
   - Click "Deploy"

6. **Monitor Logs**
   - Click on your deployment
   - Go to "Deployments" tab
   - View logs to ensure bot started successfully

### Expected Output
```
╔═══════════════════════════════════════════════════════════╗
║          🚀 NAGU ULTRA DOWNLOADER - INITIALIZING         ║
╚═══════════════════════════════════════════════════════════╝

📋 DIAGNOSTIC CHECK - Cookie Files:
────────────────────────────────────────────────────────────
  cookies_youtube.txt       : ✅ EXISTS (2048 bytes)
  cookies_instagram.txt     : ✅ EXISTS (1536 bytes)
  cookies_music.txt         : ✅ EXISTS (1024 bytes)
────────────────────────────────────────────────────────────

╔═══════════════════════════════════════════════════════════╗
║              🚀 BOT STARTING - POLLING MODE              ║
╚═══════════════════════════════════════════════════════════╝
```

---

## 🟣 Heroku Deployment

### Prerequisites
- Heroku account
- Heroku CLI installed

### Steps

1. **Login to Heroku**
   ```bash
   heroku login
   ```

2. **Create Heroku App**
   ```bash
   heroku create nagu-downloader-bot
   ```

3. **Add Buildpacks**
   ```bash
   heroku buildpacks:add --index 1 heroku/python
   heroku buildpacks:add --index 2 https://github.com/jonathanong/heroku-buildpack-ffmpeg-latest.git
   ```

4. **Configure Environment**
   ```bash
   heroku config:set PYTHONUNBUFFERED=1
   ```

5. **Deploy**
   ```bash
   git push heroku main
   ```

6. **Scale Dyno**
   ```bash
   heroku ps:scale web=1
   ```

7. **View Logs**
   ```bash
   heroku logs --tail
   ```

### Cost
- Free tier available (550-1000 hours/month)
- Hobby tier: $7/month (always on)

---

## 🐳 Docker Deployment

### Local Docker

1. **Build Image**
   ```bash
   docker build -t nagu-downloader .
   ```

2. **Run Container**
   ```bash
   docker run -d \
     --name nagu-bot \
     --restart unless-stopped \
     nagu-downloader
   ```

3. **View Logs**
   ```bash
   docker logs -f nagu-bot
   ```

4. **Stop Container**
   ```bash
   docker stop nagu-bot
   ```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  bot:
    build: .
    container_name: nagu-downloader
    restart: unless-stopped
    volumes:
      - ./cookies_youtube.txt:/app/cookies_youtube.txt
      - ./cookies_instagram.txt:/app/cookies_instagram.txt
    environment:
      - PYTHONUNBUFFERED=1
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

Run with:
```bash
docker-compose up -d
```

---

## 🖥️ VPS Deployment

### Prerequisites
- VPS with Ubuntu 20.04+ (DigitalOcean, Linode, AWS EC2, etc.)
- SSH access
- Sudo privileges

### Steps

1. **Connect to VPS**
   ```bash
   ssh user@your-vps-ip
   ```

2. **Update System**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

3. **Install Dependencies**
   ```bash
   sudo apt install -y python3.11 python3-pip ffmpeg git curl
   ```

4. **Clone Repository**
   ```bash
   git clone https://github.com/yourusername/nagu-ultra-downloader.git
   cd nagu-ultra-downloader
   ```

5. **Install Python Packages**
   ```bash
   pip3 install -r requirements.txt
   ```

6. **Configure Bot**
   - Set BOT_TOKEN environment variable
   - Upload cookie files

7. **Create Systemd Service**
   
   Create `/etc/systemd/system/nagu-bot.service`:
   ```ini
   [Unit]
   Description=NAGU Ultra Downloader Bot
   After=network.target

   [Service]
   Type=simple
   User=your-username
   WorkingDirectory=/home/your-username/nagu-ultra-downloader
   Environment="BOT_TOKEN=your_token_here"
   ExecStart=/usr/bin/python3 /home/your-username/nagu-ultra-downloader/bot.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

8. **Enable and Start Service**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable nagu-bot
   sudo systemctl start nagu-bot
   ```

9. **Check Status**
   ```bash
   sudo systemctl status nagu-bot
   ```

10. **View Logs**
    ```bash
    sudo journalctl -u nagu-bot -f
    ```

### Using Screen (Alternative)

```bash
# Install screen
sudo apt install screen

# Create new screen session
screen -S nagu-bot

# Run bot
python3 bot.py

# Detach: Press Ctrl+A then D

# Reattach
screen -r nagu-bot
```

---

## 🔧 Troubleshooting

### Bot Not Starting

**Check logs:**
```bash
# Railway: View in dashboard
# Heroku: heroku logs --tail
# Docker: docker logs nagu-bot
# VPS: sudo journalctl -u nagu-bot -f
```

**Common issues:**
1. Missing bot token
2. Cookie files not found
3. FFmpeg not installed
4. Port conflicts

### Cookie Issues

**Symptoms:**
- "Empty media response" (Instagram)
- "Video unavailable" (YouTube)
- Authentication errors

**Solutions:**
1. Re-export cookies from logged-in browser
2. Ensure Netscape format
3. Check file permissions
4. Verify cookie expiration dates

### Memory Issues

**If bot crashes due to memory:**

1. **Reduce concurrent downloads:**
   ```python
   semaphore = asyncio.Semaphore(4)  # Reduce from 8 to 4
   ```

2. **Increase swap space (VPS):**
   ```bash
   sudo fallocate -l 2G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```

3. **Upgrade VPS plan**

### FFmpeg Errors

**Install latest FFmpeg:**

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# From source (latest version)
sudo add-apt-repository ppa:savoury1/ffmpeg4
sudo apt update
sudo apt install ffmpeg
```

### Proxy Issues

**If proxies are slow/blocked:**

1. Test proxies:
   ```bash
   curl -x http://user:pass@ip:port https://www.google.com
   ```

2. Remove slow proxies from `PROXIES` list

3. Use free proxy services or VPN

### Rate Limiting

**If getting rate limited:**

1. Add more proxies
2. Increase delays between requests
3. Use residential proxies
4. Implement request queuing

---

## 📊 Monitoring

### Health Checks

**Railway:**
- Built-in health monitoring
- Auto-restart on failure

**Custom health check endpoint:**
```python
@dp.message(F.text == "/health")
async def health_check(m: Message):
    await m.answer("✅ Bot is running!")
```

### Performance Metrics

Monitor:
- Response times
- Success/failure rates
- Memory usage
- CPU usage
- Download speeds

### Logging

**Increase log verbosity:**
```python
logging.basicConfig(level=logging.DEBUG)
```

**Log to file:**
```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
```

---

## 🔄 Updates

### Update Bot Code

**Railway:**
```bash
git pull origin main
git push  # Auto-deploys
```

**Heroku:**
```bash
git pull origin main
git push heroku main
```

**VPS:**
```bash
cd nagu-ultra-downloader
git pull origin main
sudo systemctl restart nagu-bot
```

**Docker:**
```bash
docker-compose down
git pull origin main
docker-compose up -d --build
```

---

## 🆘 Support

If you encounter issues:

1. Check logs first
2. Review this troubleshooting guide
3. Search GitHub issues
4. Contact: [@bhosadih](https://t.me/bhosadih)

---

## 📝 Best Practices

1. **Regular cookie updates** (every 2-4 weeks)
2. **Monitor logs** for errors
3. **Keep dependencies updated**
4. **Backup configuration** regularly
5. **Use environment variables** for sensitive data
6. **Implement rate limiting** to avoid bans
7. **Test locally** before deploying

---

<div align="center">

**⟣—◈ NAGU ULTRA TECHNOLOGY ◈—⟢**

Made with ❤️ for the community

</div>
