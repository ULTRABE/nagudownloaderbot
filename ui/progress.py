"""Progress bar utilities"""
from typing import Optional

def create_progress_bar(current: int, total: int, length: int = 14) -> str:
    """
    Create a text-based progress bar
    
    Args:
        current: Current progress value
        total: Total value
        length: Length of progress bar in characters
    
    Returns:
        Formatted progress bar string with percentage
    """
    if total == 0:
        return f"{'░' * length} 0%"
    
    filled = int(length * current / total)
    filled = min(filled, length)  # Ensure we don't exceed length
    bar = '█' * filled + '░' * (length - filled)
    percent = int(100 * current / total)
    return f"{bar} {percent}%"

class ProgressBar:
    """
    Progress bar manager for real-time updates
    """
    
    def __init__(self, total: int, length: int = 14):
        self.total = total
        self.current = 0
        self.length = length
        self.current_item: Optional[str] = None
        self.current_item_progress: int = 0
    
    def update(self, current: int):
        """Update main progress"""
        self.current = min(current, self.total)
    
    def increment(self):
        """Increment main progress by 1"""
        self.current = min(self.current + 1, self.total)
    
    def set_current_item(self, item: str, progress: int = 0):
        """Set current item being processed"""
        self.current_item = item
        self.current_item_progress = progress
    
    def update_item_progress(self, progress: int):
        """Update current item progress"""
        self.current_item_progress = min(progress, 100)
    
    def get_main_bar(self) -> str:
        """Get main progress bar"""
        return create_progress_bar(self.current, self.total, self.length)
    
    def get_item_bar(self) -> str:
        """Get current item progress bar"""
        if self.current_item_progress == 0:
            return f"{'░' * self.length} 0%"
        filled = int(self.length * self.current_item_progress / 100)
        filled = min(filled, self.length)
        bar = '█' * filled + '░' * (self.length - filled)
        return f"{bar} {self.current_item_progress}%"
    
    def format_spotify_progress(self) -> str:
        """Format Spotify-style progress display"""
        main_bar = self.get_main_bar()
        
        if self.current_item:
            item_bar = self.get_item_bar()
            return f"""🎵 Downloading Spotify Playlist
{main_bar}

Now downloading:
{self.current_item}
{item_bar}"""
        else:
            return f"""🎵 Downloading Spotify Playlist
{main_bar}

Preparing next track..."""
