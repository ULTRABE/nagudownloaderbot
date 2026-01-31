"""User state management for Spotify downloads"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from utils.redis_client import redis_client
from utils.logger import logger

class UserStateManager:
    """Manages user registration, bot block status, and cooldowns"""
    
    def __init__(self):
        self.cooldown_duration = timedelta(hours=3)
    
    def _get_started_key(self, user_id: int) -> str:
        """Get Redis key for user started status"""
        return f"user:started:{user_id}"
    
    def _get_blocked_key(self, user_id: int) -> str:
        """Get Redis key for bot blocked status"""
        return f"user:blocked:{user_id}"
    
    def _get_cooldown_key(self, user_id: int) -> str:
        """Get Redis key for cooldown status"""
        return f"user:cooldown:{user_id}"
    
    async def mark_user_started(self, user_id: int) -> bool:
        """
        Mark user as having started the bot
        
        Args:
            user_id: User ID
        
        Returns:
            True if successful
        """
        try:
            key = self._get_started_key(user_id)
            await redis_client.set(key, "1")
            logger.info(f"User {user_id} marked as started")
            return True
        except Exception as e:
            logger.error(f"Failed to mark user started: {e}")
            return False
    
    async def has_started_bot(self, user_id: int) -> bool:
        """
        Check if user has started the bot
        
        Args:
            user_id: User ID
        
        Returns:
            True if user has started bot
        """
        try:
            key = self._get_started_key(user_id)
            result = await redis_client.get(key)
            return result == "1"
        except Exception as e:
            logger.error(f"Failed to check user started: {e}")
            return False
    
    async def mark_user_blocked(self, user_id: int) -> bool:
        """
        Mark user as having blocked the bot
        
        Args:
            user_id: User ID
        
        Returns:
            True if successful
        """
        try:
            key = self._get_blocked_key(user_id)
            await redis_client.set(key, "1")
            logger.info(f"User {user_id} marked as blocked")
            return True
        except Exception as e:
            logger.error(f"Failed to mark user blocked: {e}")
            return False
    
    async def mark_user_unblocked(self, user_id: int) -> bool:
        """
        Mark user as having unblocked the bot
        
        Args:
            user_id: User ID
        
        Returns:
            True if successful
        """
        try:
            key = self._get_blocked_key(user_id)
            await redis_client.delete(key)
            logger.info(f"User {user_id} marked as unblocked")
            return True
        except Exception as e:
            logger.error(f"Failed to mark user unblocked: {e}")
            return False
    
    async def has_blocked_bot(self, user_id: int) -> bool:
        """
        Check if user has blocked the bot
        
        Args:
            user_id: User ID
        
        Returns:
            True if user has blocked bot
        """
        try:
            key = self._get_blocked_key(user_id)
            result = await redis_client.get(key)
            return result == "1"
        except Exception as e:
            logger.error(f"Failed to check user blocked: {e}")
            return False
    
    async def apply_cooldown(self, user_id: int) -> bool:
        """
        Apply 3-hour cooldown to user
        
        Args:
            user_id: User ID
        
        Returns:
            True if successful
        """
        try:
            key = self._get_cooldown_key(user_id)
            until = (datetime.now() + self.cooldown_duration).timestamp()
            await redis_client.set(key, str(until))
            logger.info(f"Applied 3-hour cooldown to user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to apply cooldown: {e}")
            return False
    
    async def is_on_cooldown(self, user_id: int) -> tuple[bool, Optional[int]]:
        """
        Check if user is on cooldown
        
        Args:
            user_id: User ID
        
        Returns:
            Tuple of (is_on_cooldown, minutes_remaining)
        """
        try:
            key = self._get_cooldown_key(user_id)
            until_str = await redis_client.get(key)
            
            if not until_str:
                return False, None
            
            until_timestamp = float(until_str)
            now = datetime.now().timestamp()
            
            if now > until_timestamp:
                # Cooldown expired, remove it
                await redis_client.delete(key)
                return False, None
            
            # Calculate remaining time
            remaining_seconds = int(until_timestamp - now)
            remaining_minutes = remaining_seconds // 60
            
            return True, remaining_minutes
        except Exception as e:
            logger.error(f"Failed to check cooldown: {e}")
            return False, None
    
    async def remove_cooldown(self, user_id: int) -> bool:
        """
        Remove cooldown from user (admin override)
        
        Args:
            user_id: User ID
        
        Returns:
            True if successful
        """
        try:
            key = self._get_cooldown_key(user_id)
            await redis_client.delete(key)
            logger.info(f"Removed cooldown from user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove cooldown: {e}")
            return False

# Global user state manager instance
user_state_manager = UserStateManager()
