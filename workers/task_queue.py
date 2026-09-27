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


def get_queue_stats() -> dict:
    """
    Snapshot of current global concurrency usage, for /status.

    asyncio.Semaphore doesn't expose a public "in use" count, so we read the
    internal `_value` (remaining permits) and derive used = total - remaining.
    This is diagnostic-only — never used for gating decisions.
    """
    def _used(sem: asyncio.Semaphore, total: int) -> int:
        try:
            return max(0, total - sem._value)
        except Exception:
            return 0

    downloads_used = _used(download_semaphore, config.MAX_CONCURRENT_DOWNLOADS)
    music_used = _used(music_semaphore, config.MAX_CONCURRENT_MUSIC)
    spotify_used = _used(spotify_semaphore, config.MAX_CONCURRENT_SPOTIFY)

    return {
        "downloads_used": downloads_used,
        "downloads_total": config.MAX_CONCURRENT_DOWNLOADS,
        "music_used": music_used,
        "music_total": config.MAX_CONCURRENT_MUSIC,
        "spotify_used": spotify_used,
        "spotify_total": config.MAX_CONCURRENT_SPOTIFY,
        "active_jobs": downloads_used + music_used + spotify_used,
    }
