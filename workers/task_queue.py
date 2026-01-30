"""Task queue and concurrency management"""
import asyncio
from core.config import config

# Semaphores for rate limiting and concurrency control
download_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_DOWNLOADS)
music_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_MUSIC)
spotify_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_SPOTIFY)
