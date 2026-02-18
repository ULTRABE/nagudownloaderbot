"""Task queue and concurrency management"""
import asyncio
from core.config import config

# ─── Global semaphores ────────────────────────────────────────────────────────
# These control how many concurrent downloads run globally

download_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_DOWNLOADS)
music_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_MUSIC)
spotify_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_SPOTIFY)

# ─── Note ─────────────────────────────────────────────────────────────────────
# Per-user concurrency is handled in utils/watchdog.py via acquire_user_slot()
# Duplicate URL detection is also in utils/watchdog.py via mark_url_processing()
