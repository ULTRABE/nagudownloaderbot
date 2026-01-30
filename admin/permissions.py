"""Admin permission detection and management"""
import asyncio
from typing import Optional
from aiogram import Bot
from aiogram.types import ChatMemberOwner, ChatMemberAdministrator
from utils.redis_client import redis_client
from utils.logger import logger

class PermissionManager:
    """Manages admin permissions with caching"""
    
    def __init__(self):
        self.cache_ttl = 300  # 5 minutes cache
    
    def _get_admin_cache_key(self, chat_id: int, user_id: int) -> str:
        """Get Redis key for admin cache"""
        return f"admin_cache:{chat_id}:{user_id}"
    
    def _get_admins_list_key(self, chat_id: int) -> str:
        """Get Redis key for admins list"""
        return f"admins:{chat_id}"
    
    async def is_admin(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        """
        Check if user is admin (creator or administrator)
        
        Args:
            bot: Bot instance
            chat_id: Chat ID
            user_id: User ID
        
        Returns:
            True if user is admin
        """
        # Check cache first
        cache_key = self._get_admin_cache_key(chat_id, user_id)
        
        try:
            cached = await redis_client.get(cache_key)
            if cached is not None:
                return cached == "1"
        except Exception as e:
            logger.warning(f"Redis cache read failed: {e}")
        
        # Check with Telegram API
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            is_admin = isinstance(member, (ChatMemberOwner, ChatMemberAdministrator))
            
            # Cache result
            try:
                await redis_client.setex(cache_key, self.cache_ttl, "1" if is_admin else "0")
            except Exception as e:
                logger.warning(f"Redis cache write failed: {e}")
            
            return is_admin
        except Exception as e:
            logger.error(f"Failed to check admin status: {e}")
            return False
    
    async def is_creator(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        """
        Check if user is chat creator
        
        Args:
            bot: Bot instance
            chat_id: Chat ID
            user_id: User ID
        
        Returns:
            True if user is creator
        """
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            return isinstance(member, ChatMemberOwner)
        except Exception as e:
            logger.error(f"Failed to check creator status: {e}")
            return False
    
    async def add_bot_admin(self, chat_id: int, user_id: int):
        """
        Add user to bot's admin list (for custom permissions)
        
        Args:
            chat_id: Chat ID
            user_id: User ID
        """
        try:
            key = self._get_admins_list_key(chat_id)
            await redis_client.sadd(key, str(user_id))
            logger.info(f"Added bot admin: {user_id} in chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to add bot admin: {e}")
    
    async def remove_bot_admin(self, chat_id: int, user_id: int):
        """
        Remove user from bot's admin list
        
        Args:
            chat_id: Chat ID
            user_id: User ID
        """
        try:
            key = self._get_admins_list_key(chat_id)
            await redis_client.srem(key, str(user_id))
            logger.info(f"Removed bot admin: {user_id} in chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to remove bot admin: {e}")
    
    async def is_bot_admin(self, chat_id: int, user_id: int) -> bool:
        """
        Check if user is in bot's admin list
        
        Args:
            chat_id: Chat ID
            user_id: User ID
        
        Returns:
            True if user is bot admin
        """
        try:
            key = self._get_admins_list_key(chat_id)
            members = await redis_client.smembers(key)
            return str(user_id) in [str(m) for m in members]
        except Exception as e:
            logger.error(f"Failed to check bot admin: {e}")
            return False
    
    async def clear_cache(self, chat_id: int, user_id: Optional[int] = None):
        """
        Clear admin cache
        
        Args:
            chat_id: Chat ID
            user_id: Optional user ID (if None, clears all for chat)
        """
        try:
            if user_id:
                cache_key = self._get_admin_cache_key(chat_id, user_id)
                await redis_client.delete(cache_key)
            else:
                # Clear all admin caches for this chat
                pattern = f"admin_cache:{chat_id}:*"
                keys = await redis_client.keys(pattern)
                if keys:
                    await redis_client.delete(*keys)
            logger.info(f"Cleared admin cache for chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")

# Global permission manager instance
permission_manager = PermissionManager()
