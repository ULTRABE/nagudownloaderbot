"""Rate limiter for Telegram API calls to prevent flood control"""
import time
import asyncio
from typing import Dict, Optional
from utils.logger import logger

class RateLimiter:
    """
    Rate limiter to prevent Telegram flood control
    
    Telegram limits:
    - EditMessageText: Max 1 edit per second per chat
    - SendMessage: Max 30 messages per second globally
    """
    
    def __init__(self):
        # Track last update time per chat_id + message_id
        self.last_edit: Dict[str, float] = {}
        # Minimum interval between edits (seconds)
        self.min_edit_interval = 2.0  # 2 seconds between edits
        # Track message content to avoid duplicate edits
        self.last_content: Dict[str, str] = {}
    
    async def can_edit(self, chat_id: int, message_id: int, content: str) -> bool:
        """
        Check if we can edit a message
        
        Args:
            chat_id: Chat ID
            message_id: Message ID
            content: New message content
        
        Returns:
            True if edit is allowed, False if should skip
        """
        key = f"{chat_id}:{message_id}"
        current_time = time.time()
        
        # Check if content is the same (avoid "message not modified" error)
        if key in self.last_content and self.last_content[key] == content:
            return False
        
        # Check if enough time has passed since last edit
        if key in self.last_edit:
            time_since_last = current_time - self.last_edit[key]
            if time_since_last < self.min_edit_interval:
                # Not enough time passed, skip this update
                return False
        
        # Update tracking
        self.last_edit[key] = current_time
        self.last_content[key] = content
        return True
    
    async def wait_if_needed(self, chat_id: int, message_id: int) -> None:
        """
        Wait if necessary before editing a message
        
        Args:
            chat_id: Chat ID
            message_id: Message ID
        """
        key = f"{chat_id}:{message_id}"
        current_time = time.time()
        
        if key in self.last_edit:
            time_since_last = current_time - self.last_edit[key]
            if time_since_last < self.min_edit_interval:
                wait_time = self.min_edit_interval - time_since_last
                await asyncio.sleep(wait_time)
        
        self.last_edit[key] = time.time()
    
    def reset(self, chat_id: int, message_id: int) -> None:
        """
        Reset rate limit for a specific message
        
        Args:
            chat_id: Chat ID
            message_id: Message ID
        """
        key = f"{chat_id}:{message_id}"
        if key in self.last_edit:
            del self.last_edit[key]
        if key in self.last_content:
            del self.last_content[key]
    
    def cleanup_old_entries(self, max_age: float = 3600) -> None:
        """
        Clean up old entries (older than max_age seconds)
        
        Args:
            max_age: Maximum age in seconds (default 1 hour)
        """
        current_time = time.time()
        keys_to_remove = []
        
        for key, timestamp in self.last_edit.items():
            if current_time - timestamp > max_age:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            if key in self.last_edit:
                del self.last_edit[key]
            if key in self.last_content:
                del self.last_content[key]
        
        if keys_to_remove:
            logger.debug(f"Cleaned up {len(keys_to_remove)} old rate limit entries")

# Global rate limiter instance
rate_limiter = RateLimiter()
