"""Redis client wrapper"""
from typing import Optional, List, Set
from upstash_redis import Redis
from core.config import config
from .logger import logger

class RedisClient:
    """Redis client wrapper with error handling"""
    
    def __init__(self):
        self.client: Optional[Redis] = None
        self._connect()
    
    def _connect(self):
        """Initialize Redis connection"""
        try:
            if config.REDIS_URL and config.REDIS_TOKEN:
                self.client = Redis(url=config.REDIS_URL, token=config.REDIS_TOKEN)
                logger.info("Redis connected successfully")
            else:
                logger.warning("Redis credentials not provided - running without Redis")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self.client = None
    
    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        return self.client is not None
    
    # Key generators
    def get_admin_key(self, chat_id: int) -> str:
        return f"admins:{chat_id}"
    
    def get_mute_key(self, chat_id: int, user_id: int) -> str:
        return f"mute:{chat_id}:{user_id}"
    
    def get_filter_key(self, chat_id: int) -> str:
        return f"filters:{chat_id}"
    
    def get_blocklist_key(self, chat_id: int) -> str:
        return f"blocklist:{chat_id}"
    
    # Set operations
    def sadd(self, key: str, *values) -> bool:
        """Add members to set"""
        if not self.client:
            return False
        try:
            self.client.sadd(key, *values)
            return True
        except Exception as e:
            logger.error(f"Redis SADD error: {e}")
            return False
    
    def srem(self, key: str, *values) -> bool:
        """Remove members from set"""
        if not self.client:
            return False
        try:
            self.client.srem(key, *values)
            return True
        except Exception as e:
            logger.error(f"Redis SREM error: {e}")
            return False
    
    def smembers(self, key: str) -> Set[str]:
        """Get all members of set"""
        if not self.client:
            return set()
        try:
            result = self.client.smembers(key)
            return set(result) if result else set()
        except Exception as e:
            logger.error(f"Redis SMEMBERS error: {e}")
            return set()
    
    # String operations
    def set(self, key: str, value: str) -> bool:
        """Set key value"""
        if not self.client:
            return False
        try:
            self.client.set(key, value)
            return True
        except Exception as e:
            logger.error(f"Redis SET error: {e}")
            return False
    
    def get(self, key: str) -> Optional[str]:
        """Get key value"""
        if not self.client:
            return None
        try:
            return self.client.get(key)
        except Exception as e:
            logger.error(f"Redis GET error: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete key"""
        if not self.client:
            return False
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis DELETE error: {e}")
            return False

# Global Redis client instance
redis_client = RedisClient()
