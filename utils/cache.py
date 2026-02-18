"""
URL Cache — SHA256-based instant re-delivery system.

Strategy:
  hash = SHA256(url + format_tag)
  If Telegram file_id cached → send instantly (no re-download, no re-encode).
  Cache stored in Redis with 24h TTL.

Usage:
    from utils.cache import url_cache

    file_id = await url_cache.get(url, "video")
    if file_id:
        await bot.send_video(chat_id, file_id)
        return

    # ... download and encode ...

    await url_cache.set(url, "video", sent_message.video.file_id)
"""
import hashlib
from typing import Optional
from utils.redis_client import redis_client
from utils.logger import logger

# Cache TTL: 24 hours
_CACHE_TTL = 86400

# Key prefix
_PREFIX = "cache:fileid:"


def _make_key(url: str, fmt: str) -> str:
    """Deterministic cache key from URL + format tag"""
    raw = f"{url}:{fmt}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:32]
    return f"{_PREFIX}{h}"


class URLCache:
    """Telegram file_id cache backed by Redis"""

    async def get(self, url: str, fmt: str) -> Optional[str]:
        """
        Look up cached file_id for url+format.
        Returns file_id string or None if not cached.
        """
        try:
            key = _make_key(url, fmt)
            result = await redis_client.get(key)
            if result:
                logger.debug(f"Cache HIT: {url[:50]} [{fmt}]")
            return result
        except Exception as e:
            logger.debug(f"Cache get error: {e}")
            return None

    async def set(self, url: str, fmt: str, file_id: str) -> bool:
        """
        Store file_id for url+format with 24h TTL.
        Returns True on success.
        """
        try:
            key = _make_key(url, fmt)
            ok = await redis_client.setex(key, _CACHE_TTL, file_id)
            if ok:
                logger.debug(f"Cache SET: {url[:50]} [{fmt}]")
            return ok
        except Exception as e:
            logger.debug(f"Cache set error: {e}")
            return False

    async def invalidate(self, url: str, fmt: str) -> bool:
        """Remove cached entry"""
        try:
            key = _make_key(url, fmt)
            return await redis_client.delete(key)
        except Exception:
            return False


# Global cache instance
url_cache = URLCache()
