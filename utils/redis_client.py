"""Async Redis client wrapper"""
import asyncio
from typing import Optional, Any, List
from upstash_redis import Redis
from core.config import config
from utils.logger import logger

class AsyncRedisClient:
    """Async wrapper for Upstash Redis client"""
    
    def __init__(self):
        self.client: Optional[Redis] = None
        self._initialized = False
    
    def initialize(self):
        """Initialize Redis connection"""
        if self._initialized:
            return
        
        try:
            if config.REDIS_URL and config.REDIS_TOKEN:
                self.client = Redis(url=config.REDIS_URL, token=config.REDIS_TOKEN)
                self._initialized = True
                logger.info("Redis client initialized")
            else:
                logger.warning("Redis credentials not configured")
        except Exception as e:
            logger.error(f"Redis initialization failed: {e}")
            self.client = None
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis"""
        if not self.client:
            return None
        try:
            return await asyncio.to_thread(self.client.get, key)
        except Exception as e:
            logger.error(f"Redis GET failed for {key}: {e}")
            return None
    
    async def set(self, key: str, value: Any) -> bool:
        """Set value in Redis"""
        if not self.client:
            return False
        try:
            await asyncio.to_thread(self.client.set, key, value)
            return True
        except Exception as e:
            logger.error(f"Redis SET failed for {key}: {e}")
            return False
    
    async def setex(self, key: str, seconds: int, value: Any) -> bool:
        """Set value with expiration"""
        if not self.client:
            return False
        try:
            await asyncio.to_thread(self.client.setex, key, seconds, value)
            return True
        except Exception as e:
            logger.error(f"Redis SETEX failed for {key}: {e}")
            return False
    
    async def delete(self, *keys: str) -> bool:
        """Delete keys from Redis"""
        if not self.client:
            return False
        try:
            await asyncio.to_thread(self.client.delete, *keys)
            return True
        except Exception as e:
            logger.error(f"Redis DELETE failed: {e}")
            return False
    
    async def sadd(self, key: str, *members: Any) -> bool:
        """Add members to set"""
        if not self.client:
            return False
        try:
            await asyncio.to_thread(self.client.sadd, key, *members)
            return True
        except Exception as e:
            logger.error(f"Redis SADD failed for {key}: {e}")
            return False
    
    async def srem(self, key: str, *members: Any) -> bool:
        """Remove members from set"""
        if not self.client:
            return False
        try:
            await asyncio.to_thread(self.client.srem, key, *members)
            return True
        except Exception as e:
            logger.error(f"Redis SREM failed for {key}: {e}")
            return False
    
    async def smembers(self, key: str) -> List[str]:
        """Get all members of set"""
        if not self.client:
            return []
        try:
            result = await asyncio.to_thread(self.client.smembers, key)
            return list(result) if result else []
        except Exception as e:
            logger.error(f"Redis SMEMBERS failed for {key}: {e}")
            return []
    
    async def keys(self, pattern: str) -> List[str]:
        """Get keys matching pattern"""
        if not self.client:
            return []
        try:
            result = await asyncio.to_thread(self.client.keys, pattern)
            return list(result) if result else []
        except Exception as e:
            logger.error(f"Redis KEYS failed for {pattern}: {e}")
            return []
    
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        if not self.client:
            return False
        try:
            result = await asyncio.to_thread(self.client.exists, key)
            return bool(result)
        except Exception as e:
            logger.error(f"Redis EXISTS failed for {key}: {e}")
            return False
    
    async def ttl(self, key: str) -> int:
        """Get time to live for key"""
        if not self.client:
            return -1
        try:
            return await asyncio.to_thread(self.client.ttl, key)
        except Exception as e:
            logger.error(f"Redis TTL failed for {key}: {e}")
            return -1

# Global Redis client instance
redis_client = AsyncRedisClient()
