"""Progress bar and real-time update system"""
from typing import Optional

def create_progress_bar(current: int, total: int, length: int = 12) -> str:
    """
    Create clean progress bar
    
    Args:
        current: Current progress value
        total: Total value
        length: Bar length in characters
    
    Returns:
        Progress bar with percentage
    """
    if total == 0:
        return f"{'░' * length} 0%"
    
    percent = min(100, int(100 * current / total))
    filled = int(length * percent / 100)
    filled = min(filled, length)
    
    bar = '█' * filled + '░' * (length - filled)
    return f"{bar} {percent}%"

class SpotifyProgress:
    """
    Spotify download progress manager with dual progress bars
    """
    
    def __init__(self, total_songs: int):
        self.total_songs = total_songs
        self.completed_songs = 0
        self.current_song: Optional[str] = None
        self.current_song_progress: int = 0
        self.bar_length = 12
    
    def set_current_song(self, song_name: str, artist: str = ""):
        """Set currently downloading song"""
        if artist:
            self.current_song = f"{song_name} — {artist}"
        else:
            self.current_song = song_name
        self.current_song_progress = 0
    
    def update_song_progress(self, progress: int):
        """Update current song progress (0-100)"""
        self.current_song_progress = min(100, max(0, progress))
    
    def complete_song(self):
        """Mark current song as complete"""
        self.completed_songs += 1
        self.current_song = None
        self.current_song_progress = 0
    
    def get_main_progress_bar(self) -> str:
        """Get main playlist progress bar"""
        return create_progress_bar(self.completed_songs, self.total_songs, self.bar_length)
    
    def get_song_progress_bar(self) -> str:
        """Get current song progress bar"""
        filled = int(self.bar_length * self.current_song_progress / 100)
        filled = min(filled, self.bar_length)
        bar = '█' * filled + '░' * (self.bar_length - filled)
        return f"{bar} {self.current_song_progress}%"
    
    def format_message(self, phase: str = "downloading") -> str:
        """
        Format progress message for Telegram
        
        Args:
            phase: Current phase (downloading, sending, complete)
        """
        if phase == "fetching":
            return "Spotify Playlist Fetched\nStarting download..."
        
        if phase == "downloading":
            main_bar = self.get_main_progress_bar()
            
            if self.current_song:
                song_bar = self.get_song_progress_bar()
                return (
                    f"Downloading Playlist\n"
                    f"{main_bar}\n\n"
                    f"Now downloading:\n"
                    f"{self.current_song}\n"
                    f"{song_bar}"
                )
            else:
                return (
                    f"Downloading Playlist\n"
                    f"{main_bar}\n\n"
                    f"Preparing next track..."
                )
        
        if phase == "sending":
            progress_bar = create_progress_bar(self.completed_songs, self.total_songs, self.bar_length)
            return (
                f"Sending to DM\n"
                f"{progress_bar}\n\n"
                f"Sent {self.completed_songs}/{self.total_songs} songs"
            )
        
        if phase == "complete":
            return "All songs downloaded\nSending final batch..."
        
        return "Processing..."

class DownloadProgress:
    """Generic download progress tracker"""
    
    def __init__(self, total: int = 100):
        self.total = total
        self.current = 0
        self.bar_length = 12
    
    def update(self, current: int):
        """Update progress"""
        self.current = min(current, self.total)
    
    def increment(self, amount: int = 1):
        """Increment progress"""
        self.current = min(self.current + amount, self.total)
    
    def get_bar(self) -> str:
        """Get progress bar"""
        return create_progress_bar(self.current, self.total, self.bar_length)
    
    def format_message(self, title: str, subtitle: str = "") -> str:
        """Format progress message"""
        bar = self.get_bar()
        if subtitle:
            return f"{title}\n{bar}\n\n{subtitle}"
        return f"{title}\n{bar}"
