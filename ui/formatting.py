"""Message formatting utilities"""
from aiogram.types import User
from utils.helpers import mention

def format_caption(user: User, elapsed: float) -> str:
    """Format standard video caption"""
    return (
        f"₪ 𝐔𝐬𝐞𝐫: {mention(user)}\n"
        f"₪ 𝐓𝐢𝐦𝐞: {elapsed:.2f}s"
    )

def format_audio_caption(user: User, elapsed: float, title: str, artist: str, size_mb: float) -> str:
    """Format audio file caption"""
    return (
        f"𝐌𝐏𝟑 𝐃𝐎𝐖𝐍𝐋𝐎𝐀𝐃 ★\n"
        f"- - - - - - - - - - - - - - - - - - - - - - - - - - - -\n"
        f"🎵 {title}\n"
        f"🎤 {artist}\n"
        f"💾 {size_mb:.1f}MB\n"
        f"₪ 𝐔𝐬𝐞𝐫: {mention(user)}\n"
        f"₪ 𝐓𝐢𝐦𝐞: {elapsed:.2f}s"
    )
