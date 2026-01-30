"""Content filtering functions"""
from typing import List, Tuple, Optional
from utils.redis_client import redis_client
from utils.logger import logger

async def add_filter(chat_id: int, word: str):
    """Add word to filter list (substring match)"""
    if redis_client.is_connected():
        redis_client.sadd(redis_client.get_filter_key(chat_id), word.lower())
        logger.info(f"Added filter '{word}' in chat {chat_id}")

async def remove_filter(chat_id: int, word: str):
    """Remove word from filter list"""
    if redis_client.is_connected():
        redis_client.srem(redis_client.get_filter_key(chat_id), word.lower())
        logger.info(f"Removed filter '{word}' in chat {chat_id}")

async def get_filters(chat_id: int) -> List[str]:
    """Get all filtered words"""
    if not redis_client.is_connected():
        return []
    
    try:
        filters = redis_client.smembers(redis_client.get_filter_key(chat_id))
        return list(filters)
    except Exception as e:
        logger.error(f"Failed to get filters: {e}")
        return []

async def add_to_blocklist(chat_id: int, word: str):
    """Add exact word to blocklist (exact match)"""
    if redis_client.is_connected():
        redis_client.sadd(redis_client.get_blocklist_key(chat_id), word.lower())
        logger.info(f"Added to blocklist '{word}' in chat {chat_id}")

async def remove_from_blocklist(chat_id: int, word: str):
    """Remove word from blocklist"""
    if redis_client.is_connected():
        redis_client.srem(redis_client.get_blocklist_key(chat_id), word.lower())
        logger.info(f"Removed from blocklist '{word}' in chat {chat_id}")

async def get_blocklist(chat_id: int) -> List[str]:
    """Get all blocked words"""
    if not redis_client.is_connected():
        return []
    
    try:
        blocklist = redis_client.smembers(redis_client.get_blocklist_key(chat_id))
        return list(blocklist)
    except Exception as e:
        logger.error(f"Failed to get blocklist: {e}")
        return []

async def check_message_filters(chat_id: int, text: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Check if message contains filtered/blocked words
    
    Returns:
        Tuple of (is_filtered, reason)
    """
    if not text:
        return False, None
    
    text_lower = text.lower()
    
    # Check blocklist (exact word match)
    blocklist = await get_blocklist(chat_id)
    words = text_lower.split()
    for blocked in blocklist:
        if blocked in words:
            return True, f"Blocked word: {blocked}"
    
    # Check filters (substring match)
    filters = await get_filters(chat_id)
    for filtered in filters:
        if filtered in text_lower:
            return True, f"Filtered word: {filtered}"
    
    return False, None
