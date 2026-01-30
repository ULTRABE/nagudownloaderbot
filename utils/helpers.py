"""Helper utilities for the bot"""
import os
import glob
import random
from pathlib import Path
from typing import Optional
from aiogram.types import User

def mention(user: User) -> str:
    """Create clickable user mention"""
    if not user:
        return "Unknown User"
    name = user.first_name or "User"
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def get_random_cookie(folder: str) -> Optional[str]:
    """
    Get random cookie file from folder
    
    Args:
        folder: Path to cookie folder
    
    Returns:
        Path to random cookie file or None
    """
    if not os.path.exists(folder):
        return None
    
    cookies = glob.glob(f"{folder}/*.txt")
    if not cookies:
        return None
    
    return random.choice(cookies)

def resolve_pinterest_url(url: str) -> str:
    """
    Resolve shortened Pinterest URLs (pin.it)
    
    Args:
        url: Pinterest URL (may be shortened)
    
    Returns:
        Full Pinterest URL
    """
    if "pin.it/" in url:
        import subprocess
        try:
            resolved = subprocess.getoutput(
                f"curl -Ls -o /dev/null -w '%{{url_effective}}' {url}"
            )
            return resolved if resolved else url
        except:
            return url
    return url

def format_duration(seconds: float) -> str:
    """
    Format duration in human-readable format
    
    Args:
        seconds: Duration in seconds
    
    Returns:
        Formatted duration string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe file system usage
    
    Args:
        filename: Original filename
    
    Returns:
        Sanitized filename
    """
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Limit length
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200-len(ext)] + ext
    
    return filename

def ensure_dir(path: str) -> Path:
    """
    Ensure directory exists
    
    Args:
        path: Directory path
    
    Returns:
        Path object
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_file_size_mb(file_path: str) -> float:
    """
    Get file size in megabytes
    
    Args:
        file_path: Path to file
    
    Returns:
        File size in MB
    """
    try:
        return os.path.getsize(file_path) / 1024 / 1024
    except:
        return 0.0

def extract_song_metadata(filename: str) -> tuple[str, str]:
    """
    Extract artist and title from filename
    
    Args:
        filename: Song filename (without extension)
    
    Returns:
        Tuple of (artist, title)
    """
    if ' - ' in filename:
        parts = filename.split(' - ', 1)
        return parts[0].strip(), parts[1].strip()
    else:
        return "Unknown Artist", filename.strip()
