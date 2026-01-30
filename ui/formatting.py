"""Message formatting utilities - Premium UI"""
from aiogram.types import User
from utils.helpers import mention

def format_caption(user: User, elapsed: float) -> str:
    """Format standard video caption with premium quoted block style"""
    return (
        f"┌ VIDEO DOWNLOAD\n"
        f"│ ──────────────\n"
        f"│ User: {mention(user)}\n"
        f"│ Time: {elapsed:.2f}s\n"
        f"└──────────────"
    )

def format_audio_caption(user: User, elapsed: float, title: str, artist: str, size_mb: float) -> str:
    """Format audio file caption with premium quoted block style"""
    return (
        f"┌ MP3 DOWNLOAD\n"
        f"│ ──────────────\n"
        f"│ Title: {title}\n"
        f"│ Artist: {artist}\n"
        f"│ Size: {size_mb:.1f}MB\n"
        f"│ User: {mention(user)}\n"
        f"│ Time: {elapsed:.2f}s\n"
        f"└──────────────"
    )

def format_premium_panel(title: str, content: dict) -> str:
    """Format a premium quoted block panel"""
    lines = [f"┌ {title}", "│ ──────────────"]
    for key, value in content.items():
        lines.append(f"│ {key}: {value}")
    lines.append("└──────────────")
    return "\n".join(lines)
