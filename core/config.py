"""Configuration management for the bot"""
import os
import random
from pathlib import Path
from typing import List, Optional

class Config:
    """Centralized configuration management"""
    
    def __init__(self):
        # Bot credentials
        self.BOT_TOKEN = os.getenv("BOT_TOKEN", "")
        
        # Spotify API
        self.SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
        self.SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
        
        # Redis
        self.REDIS_URL = os.getenv("REDIS_URL", "")
        self.REDIS_TOKEN = os.getenv("REDIS_TOKEN", "")
        
        # Proxies
        proxies_str = os.getenv("PROXIES", "")
        self.PROXIES: List[str] = [p.strip() for p in proxies_str.split(",") if p.strip()] if proxies_str else []
        
        # Admin IDs (comma-separated)
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        self.ADMIN_IDS: List[int] = [
            int(x.strip()) for x in admin_ids_str.split(",")
            if x.strip().isdigit()
        ] if admin_ids_str else []
        
        # Cookie files and folders
        self.IG_COOKIES = "cookies_instagram.txt"
        self.YT_COOKIES_FOLDER = "yt cookies"
        self.YT_MUSIC_COOKIES_FOLDER = "yt music cookies"
        
        # Stickers
        self.IG_STICKER = os.getenv("IG_STICKER", "CAACAgIAAxkBAAEadEdpekZa1-2qYm-1a3dX0JmM_Z9uDgAC4wwAAjAT0Euml6TE9QhYWzgE")
        self.YT_STICKER = os.getenv("YT_STICKER", "CAACAgIAAxkBAAEaedlpez9LOhwF-tARQsD1V9jzU8iw1gACQjcAAgQyMEixyZ896jTkCDgE")
        self.PIN_STICKER = os.getenv("PIN_STICKER", "CAACAgIAAxkBAAEaegZpe0KJMDIkiCbudZrXhJDwBXYHqgACExIAAq3mUUhZ4G5Cm78l2DgE")
        self.MUSIC_STICKER = os.getenv("MUSIC_STICKER", "CAACAgIAAxkBAAEaegZpe0KJMDIkiCbudZrXhJDwBXYHqgACExIAAq3mUUhZ4G5Cm78l2DgE")
        
        # User agents
        self.USER_AGENTS = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
        ]
        
        # Performance settings
        self.MAX_CONCURRENT_DOWNLOADS = 8
        self.MAX_CONCURRENT_MUSIC = 3
        self.MAX_CONCURRENT_SPOTIFY = 2    # Limit to 2 concurrent playlist downloads
        self.MAX_CONCURRENT_PER_USER = 2   # Max simultaneous jobs per user
        
        # Timeout settings (seconds)
        self.DOWNLOAD_TIMEOUT = 600        # 10 minutes max per download (large playlists)
        self.FFMPEG_TIMEOUT = 180          # 3 minutes max for FFmpeg
        self.SEND_TIMEOUT = 60             # 1 minute max for Telegram send
        
        # Premium emoji support
        self.BOT_HAS_PREMIUM = os.getenv("BOT_HAS_PREMIUM", "false").lower() in ("true", "1", "yes")
        
        # Retry settings
        self.MAX_RETRIES = 2               # Max retry attempts
        
        # Telegram file size limits (MB)
        self.TG_VIDEO_LIMIT_MB = 50
        self.TG_AUDIO_LIMIT_MB = 50
        self.TG_DOC_LIMIT_MB = 50
        
        # Broadcast settings
        self.BROADCAST_RATE_LIMIT = 0.05   # Seconds between messages (20/sec)
        self.BROADCAST_CHUNK_SIZE = 30     # Messages per batch
        
        # Archive channel - DISABLED (causes flood control issues)
        # self.ARCHIVE_CHANNEL_ID = os.getenv("ARCHIVE_CHANNEL_ID", "")
        
        # Abuse handling
        self.ABUSE_TIMEOUT_HOURS = 1
        
        # Session memory duration (24 hours)
        self.SESSION_MEMORY_HOURS = 24
        
        # Video quality settings
        self.VIDEO_QUALITY_PRESET = "premium"
        self.AUDIO_BITRATE = "320k"
        
        # Health endpoint
        self.HEALTH_PORT = int(os.getenv("PORT", "8080"))
        
    def pick_proxy(self) -> Optional[str]:
        """Get random proxy from list"""
        return random.choice(self.PROXIES) if self.PROXIES else None
    
    def pick_user_agent(self) -> str:
        """Get random user agent"""
        return random.choice(self.USER_AGENTS)
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        return user_id in self.ADMIN_IDS
    
    def validate(self) -> bool:
        """Validate required configuration"""
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")
        return True

# Global config instance
config = Config()
