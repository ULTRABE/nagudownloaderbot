"""User moderation system - mute, ban, unmute, unban"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from aiogram import Bot
from aiogram.types import ChatPermissions
from utils.redis_client import redis_client
from utils.logger import logger

class ModerationManager:
    """Manages user moderation actions"""
    
    def _get_mute_key(self, chat_id: int, user_id: int) -> str:
        """Get Redis key for mute status"""
        return f"mute:{chat_id}:{user_id}"
    
    async def is_muted(self, chat_id: int, user_id: int) -> bool:
        """
        Check if user is muted
        
        Args:
            chat_id: Chat ID
            user_id: User ID
        
        Returns:
            True if user is muted
        """
        try:
            key = self._get_mute_key(chat_id, user_id)
            mute_until = await redis_client.get(key)
            
            if not mute_until:
                return False
            
            if mute_until == "permanent":
                return True
            
            # Check if mute expired
            try:
                until_timestamp = float(mute_until)
                if datetime.now().timestamp() > until_timestamp:
                    await redis_client.delete(key)
                    return False
                return True
            except:
                return False
        except Exception as e:
            logger.error(f"Failed to check mute status: {e}")
            return False
    
    async def mute_user(
        self,
        bot: Bot,
        chat_id: int,
        user_id: int,
        duration_minutes: int = 0
    ) -> tuple[bool, str]:
        """
        Mute user in chat
        
        Args:
            bot: Bot instance
            chat_id: Chat ID
            user_id: User ID
            duration_minutes: Mute duration (0 = permanent)
        
        Returns:
            Tuple of (success, message)
        """
        try:
            # Calculate until_date
            until_date = None
            if duration_minutes > 0:
                until_date = datetime.now() + timedelta(minutes=duration_minutes)
            
            # Mute in Telegram
            await bot.restrict_chat_member(
                chat_id,
                user_id,
                ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            
            # Store in Redis
            key = self._get_mute_key(chat_id, user_id)
            if duration_minutes == 0:
                await redis_client.set(key, "permanent")
            else:
                until_timestamp = until_date.timestamp()
                await redis_client.set(key, str(until_timestamp))
            
            duration_text = f"{duration_minutes} minutes" if duration_minutes > 0 else "permanently"
            logger.info(f"Muted user {user_id} in chat {chat_id} for {duration_text}")
            return True, duration_text
        except Exception as e:
            logger.error(f"Failed to mute user: {e}")
            return False, str(e)
    
    async def unmute_user(
        self,
        bot: Bot,
        chat_id: int,
        user_id: int
    ) -> tuple[bool, str]:
        """
        Unmute user in chat
        
        Args:
            bot: Bot instance
            chat_id: Chat ID
            user_id: User ID
        
        Returns:
            Tuple of (success, message)
        """
        try:
            # Unmute in Telegram
            await bot.restrict_chat_member(
                chat_id,
                user_id,
                ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_invite_users=True
                )
            )
            
            # Remove from Redis
            key = self._get_mute_key(chat_id, user_id)
            await redis_client.delete(key)
            
            logger.info(f"Unmuted user {user_id} in chat {chat_id}")
            return True, "User unmuted successfully"
        except Exception as e:
            logger.error(f"Failed to unmute user: {e}")
            return False, str(e)
    
    async def ban_user(
        self,
        bot: Bot,
        chat_id: int,
        user_id: int,
        delete_messages: bool = False
    ) -> tuple[bool, str]:
        """
        Ban user from chat
        
        Args:
            bot: Bot instance
            chat_id: Chat ID
            user_id: User ID
            delete_messages: Whether to delete user's messages
        
        Returns:
            Tuple of (success, message)
        """
        try:
            await bot.ban_chat_member(
                chat_id,
                user_id,
                revoke_messages=delete_messages
            )
            
            logger.info(f"Banned user {user_id} from chat {chat_id}")
            return True, "User banned successfully"
        except Exception as e:
            logger.error(f"Failed to ban user: {e}")
            return False, str(e)
    
    async def unban_user(
        self,
        bot: Bot,
        chat_id: int,
        user_id: int
    ) -> tuple[bool, str]:
        """
        Unban user from chat
        
        Args:
            bot: Bot instance
            chat_id: Chat ID
            user_id: User ID
        
        Returns:
            Tuple of (success, message)
        """
        try:
            await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
            
            logger.info(f"Unbanned user {user_id} from chat {chat_id}")
            return True, "User unbanned successfully"
        except Exception as e:
            logger.error(f"Failed to unban user: {e}")
            return False, str(e)

# Global moderation manager instance
moderation_manager = ModerationManager()
