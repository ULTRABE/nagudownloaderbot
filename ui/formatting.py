"""Premium UI formatting system with styled Unicode font"""
from aiogram.types import User

def mention(user: User) -> str:
    """Create clickable user mention"""
    if not user:
        return "Unknown User"
    name = user.first_name or "User"
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def format_user_id(user_id: int) -> str:
    """Format user ID as clickable link"""
    return f'<code>{user_id}</code>'

def quoted_block(content: str) -> str:
    """Wrap content in Telegram quoted block"""
    return f"<blockquote>{content}</blockquote>"

def styled_text(text: str) -> str:
    """
    Convert text to styled Unicode font
    Example: "Spotify Playlist Downloader" -> "𝐒ᴘᴏᴛɪꜰʏ 𝐏ʟᴀʏʟɪꜱᴛ 𝐃ᴏᴡɴʟᴏᴀᴅᴇʀ"
    """
    # Mapping for styled Unicode characters
    bold_map = {
        'A': '𝐀', 'B': '𝐁', 'C': '𝐂', 'D': '𝐃', 'E': '𝐄', 'F': '𝐅', 'G': '𝐆', 'H': '𝐇',
        'I': '𝐈', 'J': '𝐉', 'K': '𝐊', 'L': '𝐋', 'M': '𝐌', 'N': '𝐍', 'O': '𝐎', 'P': '𝐏',
        'Q': '𝐐', 'R': '𝐑', 'S': '𝐒', 'T': '𝐓', 'U': '𝐔', 'V': '𝐕', 'W': '𝐖', 'X': '𝐗',
        'Y': '𝐘', 'Z': '𝐙'
    }
    
    small_caps_map = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ', 'g': 'ɢ', 'h': 'ʜ',
        'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ',
        'q': 'ǫ', 'r': 'ʀ', 's': 'ꜱ', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x',
        'y': 'ʏ', 'z': 'ᴢ'
    }
    
    result = []
    for char in text:
        if char in bold_map:
            result.append(bold_map[char])
        elif char in small_caps_map:
            result.append(small_caps_map[char])
        else:
            result.append(char)
    
    return ''.join(result)

def premium_panel(title: str, lines: list[str]) -> str:
    """
    Create premium quoted panel with clean serif font
    
    Args:
        title: Panel title
        lines: List of content lines
    
    Returns:
        Formatted quoted block panel
    """
    content = f"{title}\n"
    content += "━" * 30 + "\n"
    content += "\n".join(lines)
    return quoted_block(content)

def format_download_complete(user: User, elapsed: float, platform: str) -> str:
    """Format download completion message"""
    lines = [
        f"User: {mention(user)}",
        f"Platform: {platform}",
        f"Time: {elapsed:.1f}s"
    ]
    return premium_panel("Download Complete", lines)

def format_audio_info(user: User, title: str, artist: str, size_mb: float, elapsed: float) -> str:
    """Format audio download info"""
    lines = [
        f"Title: {title}",
        f"Artist: {artist}",
        f"Size: {size_mb:.1f}MB",
        f"User: {mention(user)}",
        f"Time: {elapsed:.1f}s"
    ]
    return premium_panel("Audio Download", lines)

def format_spotify_complete(user: User, total: int, sent: int) -> str:
    """Format Spotify completion message with styled font"""
    return f"{mention(user)} — {styled_text('All')} {sent} {styled_text('songs sent to your DM successfully')}"

def format_welcome(user: User, user_id: int) -> str:
    """Format welcome message for /start with styled font"""
    username = f"@{user.username}" if user.username else "No username"
    
    lines = [
        f"🎧 {styled_text('NAGU Downloader Bot')}",
        "━" * 30,
        "",
        f"👤 {styled_text('User Information')}",
        f"  ▸ Name: {user.first_name}",
        f"  ▸ Username: {username}",
        f"  ▸ ID: {format_user_id(user_id)}",
        "",
        f"⚡ {styled_text('Quick Commands')}",
        f"  ▸ /help — {styled_text('View all features')}",
        f"  ▸ /mp3 — {styled_text('Download music')}",
        f"  ▸ {styled_text('Send any link to download')}",
        "",
        "💎 Owner: @bhosadih"
    ]
    return quoted_block("\n".join(lines))

def format_help_video() -> str:
    """Format video download help section with styled font"""
    lines = [
        f"📥 {styled_text('Video Download')}",
        "━" * 30,
        "",
        f"{styled_text('Supported Platforms')}:",
        f"  • Instagram — {styled_text('Posts, Reels, Stories')}",
        f"  • YouTube — {styled_text('Videos, Shorts, Streams')}",
        f"  • Pinterest — {styled_text('Video Pins')}",
        "",
        f"{styled_text('Usage')}:",
        f"  {styled_text('Just send the link!')}"
    ]
    return quoted_block("\n".join(lines))

def format_help_music() -> str:
    """Format music download help section with styled font"""
    lines = [
        f"🎵 {styled_text('Music Download')}",
        "━" * 30,
        "",
        f"{styled_text('Commands')}:",
        f"  /mp3 [song name] — {styled_text('Search and download')}",
        "",
        f"🎧 {styled_text('Spotify Playlists')}:",
        f"  • {styled_text('Send Spotify playlist URL in groups')}",
        f"  • {styled_text('Songs sent to your DM')}",
        f"  • {styled_text('Real-time progress updates')}"
    ]
    return quoted_block("\n".join(lines))

def format_help_info() -> str:
    """Format info commands help section"""
    lines = [
        f"ℹ️ {styled_text('Info Commands')}",
        "━" * 30,
        "",
        "  /id — Get user ID",
        "  /chatid — Get chat ID",
        "  /myinfo — Your full info"
    ]
    return quoted_block("\n".join(lines))

def format_error(error_type: str, message: str) -> str:
    """Format error message"""
    lines = [
        f"Type: {error_type}",
        f"Message: {message}"
    ]
    return premium_panel("Error", lines)

def format_user_info(user: User, chat_title: str = None) -> str:
    """Format user information panel"""
    username = f"@{user.username}" if user.username else "No username"
    lines = [
        f"Name: {user.first_name}",
        f"Username: {username}",
        f"ID: {format_user_id(user.id)}"
    ]
    if chat_title:
        lines.append(f"Chat: {chat_title}")
    return premium_panel("User Information", lines)
