"""Async Redis client wrapper with reconnect logic"""
import asyncio
from typing import Optional, Any, List, Dict
from upstash_redis import Redis
from core.config import config
from utils.logger import logger

class AsyncRedisClient:
    """Async wrapper for Upstash Redis client with auto-reconnect"""
    
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
                logger.warning("Redis credentials not configured — running without Redis")
        except Exception as e:
            logger.error(f"Redis initialization failed: {e}")
            self.client = None
    
    def _reconnect(self):
        """Attempt to reconnect to Redis"""
        try:
            if config.REDIS_URL and config.REDIS_TOKEN:
                self.client = Redis(url=config.REDIS_URL, token=config.REDIS_TOKEN)
                logger.info("Redis reconnected")
        except Exception as e:
            logger.error(f"Redis reconnect failed: {e}")
            self.client = None
    
    async def _safe_call(self, fn, *args, **kwargs):
        """Execute Redis call with reconnect on failure"""
        if not self.client:
            return None
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except Exception as e:
            err = str(e).lower()
            if "connection" in err or "timeout" in err or "reset" in err:
                logger.warning(f"Redis connection error, attempting reconnect: {e}")
                self._reconnect()
            else:
                logger.error(f"Redis error: {e}")
            return None
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis"""
        return await self._safe_call(self.client.get, key) if self.client else None
    
    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set value in Redis with optional expiry"""
        if not self.client:
            return False
        try:
            if expire:
                await asyncio.to_thread(self.client.setex, key, expire, value)
            else:
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
    
    async def scard(self, key: str) -> int:
        """Get cardinality (size) of set"""
        if not self.client:
            return 0
        try:
            result = await asyncio.to_thread(self.client.scard, key)
            return int(result) if result else 0
        except Exception as e:
            logger.error(f"Redis SCARD failed for {key}: {e}")
            return 0
    
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
    
    async def incr(self, key: str) -> int:
        """Increment integer value"""
        if not self.client:
            return 0
        try:
            result = await asyncio.to_thread(self.client.incr, key)
            return int(result) if result else 0
        except Exception as e:
            logger.error(f"Redis INCR failed for {key}: {e}")
            return 0
    
    async def incrby(self, key: str, amount: int) -> int:
        """Increment integer value by amount"""
        if not self.client:
            return 0
        try:
            result = await asyncio.to_thread(self.client.incrby, key, amount)
            return int(result) if result else 0
        except Exception as e:
            logger.error(f"Redis INCRBY failed for {key}: {e}")
            return 0
    
    async def hset(self, key: str, field: str, value: Any) -> bool:
        """Set hash field"""
        if not self.client:
            return False
        try:
            await asyncio.to_thread(self.client.hset, key, field, value)
            return True
        except Exception as e:
            logger.error(f"Redis HSET failed for {key}.{field}: {e}")
            return False
    
    async def hget(self, key: str, field: str) -> Optional[str]:
        """Get hash field"""
        if not self.client:
            return None
        try:
            result = await asyncio.to_thread(self.client.hget, key, field)
            return result
        except Exception as e:
            logger.error(f"Redis HGET failed for {key}.{field}: {e}")
            return None
    
    async def hgetall(self, key: str) -> Dict[str, str]:
        """Get all hash fields"""
        if not self.client:
            return {}
        try:
            result = await asyncio.to_thread(self.client.hgetall, key)
            return dict(result) if result else {}
        except Exception as e:
            logger.error(f"Redis HGETALL failed for {key}: {e}")
            return {}
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiry on key"""
        if not self.client:
            return False
        try:
            await asyncio.to_thread(self.client.expire, key, seconds)
            return True
        except Exception as e:
            logger.error(f"Redis EXPIRE failed for {key}: {e}")
            return False

# Global Redis client instance
redis_client = AsyncRedisClient()
