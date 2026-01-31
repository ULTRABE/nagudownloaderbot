"""Archive channel and file management system - DISABLED"""
import hashlib
import json
from typing import Optional, Dict, Any
from pathlib import Path
from aiogram import Bot
from aiogram.types import FSInputFile, Message
from core.config import config
from utils.logger import logger
from utils.redis_client import redis_client

class ArchiveManager:
    """Manages file archiving and duplicate detection - ARCHIVE CHANNEL DISABLED"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.channel_id = None  # DISABLED: Archive channel feature removed
        self.enabled = False  # DISABLED: Always False
        
    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file for duplicate detection"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    async def check_duplicate(self, file_hash: str) -> Optional[str]:
        """
        Check if file already exists in archive
        
        Returns:
            file_id if duplicate found, None otherwise
        """
        if not self.enabled or not redis_client.client:
            return None
            
        try:
            key = f"archive:hash:{file_hash}"
            file_id = await redis_client.get(key)
            return file_id
        except Exception as e:
            logger.error(f"Error checking duplicate: {e}")
            return None
    
    async def archive_file(self, file_path: str, metadata: Dict[str, Any]) -> Optional[str]:
        """
        Archive file to channel and store metadata
        
        Args:
            file_path: Path to file
            metadata: File metadata (title, artist, platform, etc.)
            
        Returns:
            file_id if successful, None otherwise
        """
        if not self.enabled:
            return None
            
        try:
            # Calculate file hash
            file_hash = self.calculate_file_hash(file_path)
            
            # Check if already archived
            existing_file_id = await self.check_duplicate(file_hash)
            if existing_file_id:
                logger.info(f"File already archived: {file_hash[:8]}...")
                return existing_file_id
            
            # Send to archive channel
            file = FSInputFile(file_path)
            caption = self._format_archive_caption(metadata)
            
            # Determine file type and send accordingly
            file_ext = Path(file_path).suffix.lower()
            if file_ext in ['.mp3', '.m4a', '.flac', '.wav']:
                msg = await self.bot.send_audio(
                    chat_id=self.channel_id,
                    audio=file,
                    caption=caption
                )
            elif file_ext in ['.mp4', '.mkv', '.avi', '.mov']:
                msg = await self.bot.send_video(
                    chat_id=self.channel_id,
                    video=file,
                    caption=caption
                )
            else:
                msg = await self.bot.send_document(
                    chat_id=self.channel_id,
                    document=file,
                    caption=caption
                )
            
            # Get file_id from message
            file_id = None
            if msg.audio:
                file_id = msg.audio.file_id
            elif msg.video:
                file_id = msg.video.file_id
            elif msg.document:
                file_id = msg.document.file_id
            
            if file_id and redis_client.client:
                # Store hash -> file_id mapping
                hash_key = f"archive:hash:{file_hash}"
                await redis_client.set(hash_key, file_id, expire=86400 * 30)  # 30 days
                
                # Store metadata
                meta_key = f"archive:meta:{file_id}"
                await redis_client.set(meta_key, json.dumps(metadata), expire=86400 * 30)
                
                logger.info(f"Archived file: {metadata.get('title', 'Unknown')} [{file_hash[:8]}...]")
            
            return file_id
            
        except Exception as e:
            logger.error(f"Error archiving file: {e}")
            return None
    
    async def get_archived_file(self, file_hash: str) -> Optional[str]:
        """Get file_id from archive by hash"""
        return await self.check_duplicate(file_hash)
    
    def _format_archive_caption(self, metadata: Dict[str, Any]) -> str:
        """Format caption for archived file"""
        lines = []
        
        if metadata.get('title'):
            lines.append(f"🎵 {metadata['title']}")
        if metadata.get('artist'):
            lines.append(f"👤 {metadata['artist']}")
        if metadata.get('platform'):
            lines.append(f"📱 {metadata['platform']}")
        if metadata.get('url'):
            lines.append(f"🔗 {metadata['url']}")
        
        # Add hash for reference
        if metadata.get('hash'):
            lines.append(f"#️⃣ {metadata['hash'][:16]}")
        
        return "\n".join(lines) if lines else "Archived Media"

# Global archive manager (initialized after bot is created)
archive_manager: Optional[ArchiveManager] = None

def init_archive_manager(bot: Bot):
    """Initialize archive manager with bot instance"""
    global archive_manager
    archive_manager = ArchiveManager(bot)
    if archive_manager.enabled:
        logger.info(f"✓ Archive channel enabled: {config.ARCHIVE_CHANNEL_ID}")
    else:
        logger.info("⚠ Archive channel disabled (ARCHIVE_CHANNEL_ID not set)")
