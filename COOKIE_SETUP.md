# 🍪 Cookie Setup Guide - NAGU DOWNLOADER BOT

## 📁 Folder Structure

Create these folders in your project root:

```
nagu-downloader/
├── yt_cookies/
│   ├── yt_cookie_1.txt
│   ├── yt_cookie_2.txt
│   ├── yt_cookie_3.txt
│   ├── yt_cookie_4.txt
│   ├── yt_cookie_5.txt
│   └── yt_cookie_6.txt
│
├── yt_music_cookies/
│   ├── ytm_cookie_1.txt
│   ├── ytm_cookie_2.txt
│   ├── ytm_cookie_3.txt
│   ├── ytm_cookie_4.txt
│   ├── ytm_cookie_5.txt
│   └── ytm_cookie_6.txt
│
├── cookies_instagram.txt
└── main.py
```

---

## 🎯 Why Cookie Rotation?

**Problem**: YouTube flags cookies after 1-2 downloads (bot detection)

**Solution**: Rotate between 5-6 different cookie files
- Each download uses a random cookie file
- Spreads requests across multiple accounts
- Avoids flagging

---

## 📝 How to Export Cookies

### 1. Install Browser Extension

**Chrome/Edge**:
- [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)

**Firefox**:
- [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

### 2. Export YouTube Cookies (5-6 accounts)

For each YouTube account:
1. Login to youtube.com
2. Click extension icon
3. Export cookies
4. Save as `yt_cookie_1.txt`, `yt_cookie_2.txt`, etc.
5. Place in `yt_cookies/` folder

### 3. Export YouTube Music Cookies (5-6 accounts)

For each YouTube Music account:
1. Login to music.youtube.com
2. Click extension icon
3. Export cookies
4. Save as `ytm_cookie_1.txt`, `ytm_cookie_2.txt`, etc.
5. Place in `yt_music_cookies/` folder

### 4. Export Instagram Cookies (1 account)

1. Login to instagram.com
2. Click extension icon
3. Export cookies
4. Save as `cookies_instagram.txt`
5. Place in root folder

---

## ⚙️ Environment Variables

Add these to your Railway/VPS:

```bash
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
```

### Get Spotify API Credentials:

1. Go to https://developer.spotify.com/dashboard
2. Click "Create an App"
3. Fill in app name and description
4. Copy Client ID and Client Secret
5. Add to environment variables

---

## 🔄 Cookie Rotation Logic

### YouTube Videos:
```python
# Tries random cookie from yt_cookies/ folder
cookie_file = get_random_cookie("yt_cookies")
```

### MP3 Search:
```python
# Tries random cookie from yt_music_cookies/ folder
cookie_file = get_random_cookie("yt_music_cookies")
```

### Instagram:
```python
# Uses single cookies_instagram.txt file
# Only as fallback (tries without cookies first)
```

---

## 📊 Expected Results

With 5-6 cookies per folder:
- **No flagging** (requests spread across accounts)
- **Fast downloads** (no delays needed)
- **High success rate** (multiple fallbacks)
- **Sustainable** (cookies last longer)

---

## 🚀 Deployment

### Railway:

1. Create folders:
   ```bash
   mkdir yt_cookies yt_music_cookies
   ```

2. Add cookie files to folders

3. Set environment variables in Railway dashboard:
   - `SPOTIFY_CLIENT_ID`
   - `SPOTIFY_CLIENT_SECRET`

4. Push to GitHub:
   ```bash
   git add .
   git commit -m "Add cookie folders"
   git push
   ```

5. Railway auto-deploys

---

## ✅ Verification

Bot startup logs should show:
```
NAGU DOWNLOADER BOT - STARTING
Semaphore: 16 concurrent downloads
Proxies: 6
YT cookies: 6 files
YT Music cookies: 6 files
```

---

## 🔧 Troubleshooting

### "No cookies found"
- Check folder names are exact: `yt_cookies` and `yt_music_cookies`
- Check files have `.txt` extension
- Check files are in Netscape format

### "Still getting flagged"
- Add more cookie files (8-10 per folder)
- Use different Google accounts
- Add delays between requests

### "Spotify not working"
- Check environment variables are set
- Verify Client ID and Secret are correct
- Check spotdl is installed

---

<div align="center">

**⟣—◈ NAGU DOWNLOADER BOT ◈—⟢**

Cookie rotation prevents flagging! 🚀

</div>
