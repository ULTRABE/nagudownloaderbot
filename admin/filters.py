"""Content filtering system"""
from typing import List, Optional, Tuple
from utils.redis_client import redis_client
from utils.logger import logger

class FilterManager:
    """Manages word filters and blocklists"""
    
    def _get_filter_key(self, chat_id: int) -> str:
        """Get Redis key for filters"""
        return f"filters:{chat_id}"
    
    def _get_blocklist_key(self, chat_id: int) -> str:
        """Get Redis key for blocklist"""
        return f"blocklist:{chat_id}"
    
    async def add_filter(self, chat_id: int, word: str) -> bool:
        """
        Add word to filter list (substring match)
        
        Args:
            chat_id: Chat ID
            word: Word to filter
        
        Returns:
            True if successful
        """
        try:
            key = self._get_filter_key(chat_id)
            await redis_client.sadd(key, word.lower())
            logger.info(f"Added filter '{word}' in chat {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add filter: {e}")
            return False
    
    async def remove_filter(self, chat_id: int, word: str) -> bool:
        """
        Remove word from filter list
        
        Args:
            chat_id: Chat ID
            word: Word to remove
        
        Returns:
            True if successful
        """
        try:
            key = self._get_filter_key(chat_id)
            await redis_client.srem(key, word.lower())
            logger.info(f"Removed filter '{word}' from chat {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove filter: {e}")
            return False
    
    async def get_filters(self, chat_id: int) -> List[str]:
        """
        Get all filtered words for chat
        
        Args:
            chat_id: Chat ID
        
        Returns:
            List of filtered words
        """
        try:
            key = self._get_filter_key(chat_id)
            return await redis_client.smembers(key)
        except Exception as e:
            logger.error(f"Failed to get filters: {e}")
            return []
    
    async def add_to_blocklist(self, chat_id: int, word: str) -> bool:
        """
        Add word to blocklist (exact word match)
        
        Args:
            chat_id: Chat ID
            word: Word to block
        
        Returns:
            True if successful
        """
        try:
            key = self._get_blocklist_key(chat_id)
            await redis_client.sadd(key, word.lower())
            logger.info(f"Added to blocklist '{word}' in chat {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add to blocklist: {e}")
            return False
    
    async def remove_from_blocklist(self, chat_id: int, word: str) -> bool:
        """
        Remove word from blocklist
        
        Args:
            chat_id: Chat ID
            word: Word to remove
        
        Returns:
            True if successful
        """
        try:
            key = self._get_blocklist_key(chat_id)
            await redis_client.srem(key, word.lower())
            logger.info(f"Removed from blocklist '{word}' in chat {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove from blocklist: {e}")
            return False
    
    async def get_blocklist(self, chat_id: int) -> List[str]:
        """
        Get all blocked words for chat
        
        Args:
            chat_id: Chat ID
        
        Returns:
            List of blocked words
        """
        try:
            key = self._get_blocklist_key(chat_id)
            return await redis_client.smembers(key)
        except Exception as e:
            logger.error(f"Failed to get blocklist: {e}")
            return []
    
    async def check_message(self, chat_id: int, text: str) -> Tuple[bool, Optional[str]]:
        """
        Check if message contains filtered or blocked words
        
        Args:
            chat_id: Chat ID
            text: Message text
        
        Returns:
            Tuple of (is_filtered, reason)
        """
        if not text:
            return False, None
        
        text_lower = text.lower()
        
        # Check blocklist (exact word match)
        try:
            blocklist = await self.get_blocklist(chat_id)
            words = text_lower.split()
            for blocked in blocklist:
                if blocked in words:
                    return True, f"Blocked word: {blocked}"
        except Exception as e:
            logger.error(f"Blocklist check failed: {e}")
        
        # Check filters (substring match)
        try:
            filters = await self.get_filters(chat_id)
            for filtered in filters:
                if filtered in text_lower:
                    return True, f"Filtered word: {filtered}"
        except Exception as e:
            logger.error(f"Filter check failed: {e}")
        
        return False, None

# Global filter manager instance
filter_manager = FilterManager()
