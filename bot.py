"""
NAGU DOWNLOADER BOT - Production Grade Refactored Version
Ultra-fast, stable, scalable Telegram music + downloader + management bot

Features:
- Instagram, Pinterest, YouTube downloaders
- MP3 search and download
- Spotify playlist downloader with real-time progress
- Full admin/moderation system
- Whisper command
- Content filters
- Fully async, non-blocking architecture
"""
import asyncio
import glob
import os

from core import config, bot, dp
from utils.logger import logger
from admin.handlers import register_admin_handlers
from downloaders.router import register_download_handlers

async def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("NAGU DOWNLOADER BOT - STARTING")
    logger.info("=" * 60)
    
    # Validate configuration
    try:
        config.validate()
        logger.info("✓ Configuration validated")
    except ValueError as e:
        logger.error(f"✗ Configuration error: {e}")
        return
    
    # Log configuration
    logger.info(f"✓ Max concurrent downloads: {config.MAX_CONCURRENT_DOWNLOADS}")
    logger.info(f"✓ Max concurrent music: {config.MAX_CONCURRENT_MUSIC}")
    logger.info(f"✓ Max concurrent Spotify: {config.MAX_CONCURRENT_SPOTIFY}")
    logger.info(f"✓ Proxies configured: {len(config.PROXIES)}")
    
    # Check cookie folders
    if os.path.exists(config.YT_COOKIES_FOLDER):
        yt_cookies = len(glob.glob(f"{config.YT_COOKIES_FOLDER}/*.txt"))
        logger.info(f"✓ YT cookies: {yt_cookies} files")
    else:
        logger.warning(f"⚠ YT cookies folder not found: {config.YT_COOKIES_FOLDER}")
    
    if os.path.exists(config.YT_MUSIC_COOKIES_FOLDER):
        music_cookies = len(glob.glob(f"{config.YT_MUSIC_COOKIES_FOLDER}/*.txt"))
        logger.info(f"✓ YT Music cookies: {music_cookies} files")
    else:
        logger.warning(f"⚠ YT Music cookies folder not found: {config.YT_MUSIC_COOKIES_FOLDER}")
    
    # Register handlers
    register_admin_handlers()
    register_download_handlers()
    logger.info("✓ All handlers registered")
    
    # Start bot
    logger.info("=" * 60)
    logger.info("BOT IS READY - Starting polling...")
    logger.info("=" * 60)
    
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        logger.info("Shutting down...")

if __name__ == "__main__":
    asyncio.run(main())
