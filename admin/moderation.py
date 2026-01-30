"""User moderation functions"""
from datetime import datetime, timedelta
from utils.redis_client import redis_client
from utils.logger import logger

async def mute_user(chat_id: int, user_id: int, duration_minutes: int = 0):
    """
    Mute user for duration (0 = permanent)
    
    Args:
        chat_id: Chat ID
        user_id: User ID to mute
        duration_minutes: Duration in minutes (0 for permanent)
    """
    if not redis_client.is_connected():
        return
    
    key = redis_client.get_mute_key(chat_id, user_id)
    
    if duration_minutes == 0:
        redis_client.set(key, "permanent")
        logger.info(f"Muted user {user_id} permanently in chat {chat_id}")
    else:
        until = (datetime.now() + timedelta(minutes=duration_minutes)).timestamp()
        redis_client.set(key, str(until))
        logger.info(f"Muted user {user_id} for {duration_minutes} minutes in chat {chat_id}")

async def unmute_user(chat_id: int, user_id: int):
    """Unmute user"""
    if redis_client.is_connected():
        redis_client.delete(redis_client.get_mute_key(chat_id, user_id))
        logger.info(f"Unmuted user {user_id} in chat {chat_id}")

async def is_muted(chat_id: int, user_id: int) -> bool:
    """Check if user is muted"""
    if not redis_client.is_connected():
        return False
    
    try:
        key = redis_client.get_mute_key(chat_id, user_id)
        mute_until = redis_client.get(key)
        
        if not mute_until:
            return False
        
        if mute_until == "permanent":
            return True
        
        # Check if mute expired
        if datetime.now().timestamp() > float(mute_until):
            redis_client.delete(key)
            return False
        
        return True
    except Exception as e:
        logger.error(f"Failed to check mute status: {e}")
        return False
