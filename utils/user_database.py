"""Per-user database for download tracking and session management"""
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from utils.redis_client import redis_client
from utils.logger import logger
from core.config import config

@dataclass
class DownloadRecord:
    """Record of a single download"""
    file_id: str
    file_hash: str
    title: str
    platform: str  # spotify, youtube, instagram, pinterest, mp3
    url: str
    status: str  # completed, failed, pending
    timestamp: float
    error: Optional[str] = None

@dataclass
class SpotifySession:
    """Spotify playlist session data"""
    playlist_url: str
    playlist_id: str
    total_tracks: int
    completed_tracks: List[str]  # Track IDs
    failed_tracks: List[Dict[str, str]]  # {track_id, title, error}
    last_updated: float
    
class UserDatabase:
    """Manages per-user download history and sessions"""
    
    def __init__(self):
        self.session_duration = config.SESSION_MEMORY_HOURS * 3600  # Convert to seconds
        
    async def add_download(self, user_id: int, record: DownloadRecord):
        """Add download record to user history"""
        if not redis_client.client:
            return
            
        try:
            key = f"user:{user_id}:downloads"
            record_data = asdict(record)
            
            # Get existing records
            existing = await redis_client.get(key)
            records = json.loads(existing) if existing else []
            
            # Add new record
            records.append(record_data)
            
            # Keep only last 100 records per user
            if len(records) > 100:
                records = records[-100:]
            
            # Save back
            await redis_client.set(key, json.dumps(records), expire=86400 * 7)  # 7 days
            
        except Exception as e:
            logger.error(f"Error adding download record: {e}")
    
    async def get_user_downloads(self, user_id: int, platform: Optional[str] = None) -> List[DownloadRecord]:
        """Get user's download history"""
        if not redis_client.client:
            return []
            
        try:
            key = f"user:{user_id}:downloads"
            data = await redis_client.get(key)
            if not data:
                return []
            
            records = json.loads(data)
            downloads = [DownloadRecord(**r) for r in records]
            
            if platform:
                downloads = [d for d in downloads if d.platform == platform]
            
            return downloads
            
        except Exception as e:
            logger.error(f"Error getting user downloads: {e}")
            return []
    
    async def save_spotify_session(self, user_id: int, session: SpotifySession):
        """Save Spotify playlist session"""
        if not redis_client.client:
            return
            
        try:
            key = f"user:{user_id}:spotify:{session.playlist_id}"
            session_data = asdict(session)
            await redis_client.set(
                key,
                json.dumps(session_data),
                expire=int(self.session_duration)
            )
            logger.info(f"Saved Spotify session for user {user_id}: {session.playlist_id}")
            
        except Exception as e:
            logger.error(f"Error saving Spotify session: {e}")
    
    async def get_spotify_session(self, user_id: int, playlist_id: str) -> Optional[SpotifySession]:
        """Get existing Spotify session"""
        if not redis_client.client:
            return None
            
        try:
            key = f"user:{user_id}:spotify:{playlist_id}"
            data = await redis_client.get(key)
            if not data:
                return None
            
            session_data = json.loads(data)
            return SpotifySession(**session_data)
            
        except Exception as e:
            logger.error(f"Error getting Spotify session: {e}")
            return None
    
    async def update_spotify_progress(
        self,
        user_id: int,
        playlist_id: str,
        completed_track: Optional[str] = None,
        failed_track: Optional[Dict[str, str]] = None
    ):
        """Update Spotify session progress"""
        session = await self.get_spotify_session(user_id, playlist_id)
        if not session:
            return
        
        if completed_track:
            if completed_track not in session.completed_tracks:
                session.completed_tracks.append(completed_track)
        
        if failed_track:
            # Check if already in failed list
            existing = next((f for f in session.failed_tracks if f['track_id'] == failed_track['track_id']), None)
            if not existing:
                session.failed_tracks.append(failed_track)
        
        session.last_updated = time.time()
        await self.save_spotify_session(user_id, session)
    
    async def is_user_blocked(self, user_id: int) -> bool:
        """Check if user is temporarily blocked for abuse"""
        if not redis_client.client:
            return False
            
        try:
            key = f"user:{user_id}:blocked"
            blocked = await redis_client.get(key)
            return bool(blocked)
            
        except Exception as e:
            logger.error(f"Error checking user block status: {e}")
            return False
    
    async def block_user(self, user_id: int, reason: str = "bot_blocked"):
        """Temporarily block user"""
        if not redis_client.client:
            return
            
        try:
            key = f"user:{user_id}:blocked"
            block_data = {
                "reason": reason,
                "blocked_at": time.time(),
                "expires_at": time.time() + (config.ABUSE_TIMEOUT_HOURS * 3600)
            }
            await redis_client.set(
                key,
                json.dumps(block_data),
                expire=config.ABUSE_TIMEOUT_HOURS * 3600
            )
            logger.warning(f"Blocked user {user_id} for {config.ABUSE_TIMEOUT_HOURS}h: {reason}")
            
        except Exception as e:
            logger.error(f"Error blocking user: {e}")
    
    async def unblock_user(self, user_id: int):
        """Manually unblock user"""
        if not redis_client.client:
            return
            
        try:
            key = f"user:{user_id}:blocked"
            await redis_client.delete(key)
            logger.info(f"Unblocked user {user_id}")
            
        except Exception as e:
            logger.error(f"Error unblocking user: {e}")
    
    async def get_block_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user block information"""
        if not redis_client.client:
            return None
            
        try:
            key = f"user:{user_id}:blocked"
            data = await redis_client.get(key)
            if not data:
                return None
            
            return json.loads(data)
            
        except Exception as e:
            logger.error(f"Error getting block info: {e}")
            return None

# Global user database instance
user_db = UserDatabase()
