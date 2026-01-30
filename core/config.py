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
        ]
        
        # Performance settings
        self.MAX_CONCURRENT_DOWNLOADS = 16
        self.MAX_CONCURRENT_MUSIC = 3
        self.MAX_CONCURRENT_SPOTIFY = 4
        
    def pick_proxy(self) -> Optional[str]:
        """Get random proxy from list"""
        return random.choice(self.PROXIES) if self.PROXIES else None
    
    def pick_user_agent(self) -> str:
        """Get random user agent"""
        return random.choice(self.USER_AGENTS)
    
    def validate(self) -> bool:
        """Validate required configuration"""
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")
        return True

# Global config instance
config = Config()
