"""Permission management"""
from typing import List
from core.bot import bot
from utils.redis_client import redis_client
from utils.logger import logger

async def is_telegram_admin(chat_id: int, user_id: int) -> bool:
    """Check if user is Telegram admin (creator or administrator)"""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ["creator", "administrator"]
    except Exception as e:
        logger.error(f"Failed to check Telegram admin status: {e}")
        return False

async def is_admin(chat_id: int, user_id: int) -> bool:
    """
    Check if user is admin (either Telegram admin or bot admin)
    First checks Telegram, then checks Redis cache
    """
    # Check Telegram admin status first
    if await is_telegram_admin(chat_id, user_id):
        # Sync to Redis for faster future checks
        await add_admin(chat_id, user_id)
        return True
    
    # Check Redis cache
    if not redis_client.is_connected():
        return False
    
    try:
        admins = redis_client.smembers(redis_client.get_admin_key(chat_id))
        return str(user_id) in [str(a) for a in admins]
    except Exception as e:
        logger.error(f"Failed to check admin from Redis: {e}")
        return False

async def add_admin(chat_id: int, user_id: int):
    """Add user as admin in Redis"""
    if redis_client.is_connected():
        redis_client.sadd(redis_client.get_admin_key(chat_id), str(user_id))
        logger.info(f"Added admin: user {user_id} in chat {chat_id}")

async def remove_admin(chat_id: int, user_id: int):
    """Remove user from admins in Redis"""
    if redis_client.is_connected():
        redis_client.srem(redis_client.get_admin_key(chat_id), str(user_id))
        logger.info(f"Removed admin: user {user_id} in chat {chat_id}")

async def get_admins(chat_id: int) -> List[int]:
    """Get list of admin user IDs"""
    if not redis_client.is_connected():
        return []
    
    try:
        admins = redis_client.smembers(redis_client.get_admin_key(chat_id))
        return [int(a) for a in admins]
    except Exception as e:
        logger.error(f"Failed to get admins: {e}")
        return []

async def sync_admins(chat_id: int):
    """Sync Telegram admins to Redis cache"""
    try:
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            await add_admin(chat_id, admin.user.id)
        logger.info(f"Synced {len(admins)} admins for chat {chat_id}")
    except Exception as e:
        logger.error(f"Failed to sync admins: {e}")
