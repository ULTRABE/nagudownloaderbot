"""
NAGU DOWNLOADER BOT — Production-grade Telegram downloader

Features:
- Instagram, Pinterest, YouTube (Shorts + Normal), Spotify (playlist + single)
- Layered extraction: API → alt config → cookies
- Inline Video/Audio buttons for YouTube
- Broadcast system (admin-only)
- Anti-stuck watchdog with timeouts
- Automatic file size handling (compress/split)
- Redis-backed state management
- Graceful shutdown
- Health endpoint
"""
import asyncio
import glob
import os
import shutil
import signal
import tempfile
import traceback
from pathlib import Path

from aiohttp import web

from core.bot import bot, dp
from core.config import config
from utils.logger import logger
from utils.redis_client import redis_client
from utils.archive import init_archive_manager
from downloaders.router import register_download_handlers

# ─── Health endpoint ──────────────────────────────────────────────────────────

async def health_handler(request):
    """Simple health check endpoint for Railway/uptime monitors"""
    return web.Response(text="OK", status=200)

async def start_health_server():
    """Start lightweight HTTP health server"""
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, "0.0.0.0", config.HEALTH_PORT)
    await site.start()
    logger.info(f"✓ Health server running on port {config.HEALTH_PORT}")
    return runner

# ─── Background temp cleanup ──────────────────────────────────────────────────

async def periodic_temp_cleanup(interval: int = 3600):
    """
    Periodically clean up stale temp files.
    Runs every `interval` seconds.
    """
    while True:
        try:
            await asyncio.sleep(interval)
            tmp_base = tempfile.gettempdir()
            cleaned = 0
            
            for entry in os.scandir(tmp_base):
                if entry.is_dir() and entry.name.startswith("tmp"):
                    try:
                        # Only remove dirs older than 30 minutes
                        import time
                        age = time.time() - entry.stat().st_mtime
                        if age > 1800:
                            shutil.rmtree(entry.path, ignore_errors=True)
                            cleaned += 1
                    except Exception:
                        pass
            
            if cleaned > 0:
                logger.info(f"Temp cleanup: removed {cleaned} stale directories")
        
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Temp cleanup error: {e}")

# ─── Graceful shutdown ────────────────────────────────────────────────────────

_shutdown_event = asyncio.Event()

def _handle_signal(sig):
    logger.info(f"Received signal {sig.name}, initiating graceful shutdown...")
    _shutdown_event.set()

# ─── Main ─────────────────────────────────────────────────────────────────────

def _check_ffmpeg() -> bool:
    """Check if ffmpeg is available on PATH"""
    return shutil.which("ffmpeg") is not None

def _check_ffprobe() -> bool:
    """Check if ffprobe is available on PATH"""
    return shutil.which("ffprobe") is not None


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

    # Check ffmpeg availability
    if _check_ffmpeg():
        logger.info("✓ ffmpeg available")
    else:
        logger.warning("⚠ ffmpeg NOT found — video encoding/splitting will fail")

    if _check_ffprobe():
        logger.info("✓ ffprobe available")
    else:
        logger.warning("⚠ ffprobe NOT found — video info detection will fail")
    
    # Initialize Redis
    redis_client.initialize()
    
    # Initialize archive manager
    init_archive_manager(bot)
    
    # Log configuration
    logger.info(f"✓ Max concurrent downloads: {config.MAX_CONCURRENT_DOWNLOADS}")
    logger.info(f"✓ Max concurrent music: {config.MAX_CONCURRENT_MUSIC}")
    logger.info(f"✓ Max concurrent Spotify: {config.MAX_CONCURRENT_SPOTIFY}")
    logger.info(f"✓ Max per-user slots: {config.MAX_CONCURRENT_PER_USER}")
    logger.info(f"✓ Proxies configured: {len(config.PROXIES)}")
    if config.ADMIN_IDS:
        logger.info(f"✓ Admin IDs: {config.ADMIN_IDS}")
    else:
        logger.warning("⚠ ADMIN_IDS not configured — /broadcast and admin commands will not work")
        logger.warning("  Set ADMIN_IDS env var to comma-separated Telegram user IDs")
    logger.info(f"✓ Premium emojis: {'enabled' if config.BOT_HAS_PREMIUM else 'disabled'}")
    logger.info(f"✓ Download timeout: {config.DOWNLOAD_TIMEOUT}s")
    
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
    register_download_handlers()
    logger.info("✓ All handlers registered")
    
    # Start health server
    health_runner = await start_health_server()
    
    # Start background cleanup task
    cleanup_task = asyncio.create_task(periodic_temp_cleanup())
    
    # Register signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: _handle_signal(s))
        except NotImplementedError:
            pass  # Windows doesn't support add_signal_handler
    
    logger.info("=" * 60)
    logger.info("BOT IS READY - Starting polling...")
    logger.info("=" * 60)

    async def _polling_with_restart():
        """Polling wrapper — restarts on unexpected errors, never crashes"""
        while not _shutdown_event.is_set():
            try:
                await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
            except asyncio.CancelledError:
                break
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"Polling crashed: {e}\n{tb}")
                if not _shutdown_event.is_set():
                    logger.info("Restarting polling in 5 seconds...")
                    await asyncio.sleep(5)

    # Start polling in background
    polling_task = asyncio.create_task(_polling_with_restart())
    
    # Wait for shutdown signal
    try:
        await _shutdown_event.wait()
    except asyncio.CancelledError:
        pass
    
    # Graceful shutdown sequence
    logger.info("Shutting down gracefully...")
    
    # Stop polling
    polling_task.cancel()
    try:
        await polling_task
    except (asyncio.CancelledError, Exception):
        pass
    
    # Stop cleanup task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    
    # Stop health server
    try:
        await health_runner.cleanup()
    except Exception:
        pass
    
    # Close bot session
    try:
        await bot.session.close()
    except Exception:
        pass
    
    logger.info("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
