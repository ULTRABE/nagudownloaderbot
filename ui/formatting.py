"""Premium UI formatting system - Clean quoted blocks with serif Unicode"""
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

def format_admin_action(action: str, target_user: User, details: str = None) -> str:
    """Format admin action confirmation"""
    lines = [
        f"Action: {action}",
        f"Target: {mention(target_user)}",
        f"ID: {format_user_id(target_user.id)}"
    ]
    if details:
        lines.append(f"Details: {details}")
    return premium_panel("Admin Action", lines)

def format_error(error_type: str, message: str) -> str:
    """Format error message"""
    lines = [
        f"Type: {error_type}",
        f"Message: {message}"
    ]
    return premium_panel("Error", lines)

def format_spotify_complete(user: User, total: int, sent: int) -> str:
    """Format Spotify completion message"""
    return f"{mention(user)} — All {sent} songs sent to your DM successfully"

def format_welcome(user: User, user_id: int) -> str:
    """Format welcome message for /start"""
    username = f"@{user.username}" if user.username else "No username"
    
    lines = [
        "Welcome to NAGU Downloader Bot",
        "━" * 30,
        "",
        "User Information",
        f"  Name: {user.first_name}",
        f"  Username: {username}",
        f"  ID: {format_user_id(user_id)}",
        "",
        "Quick Commands",
        "  /help — View all features",
        "  /mp3 — Download music",
        "  Send any link to download",
        "",
        "Owner: @bhosadih"
    ]
    return quoted_block("\n".join(lines))

def format_help_video() -> str:
    """Format video download help section"""
    lines = [
        "Video Download",
        "━" * 30,
        "",
        "Supported Platforms:",
        "  • Instagram — Posts, Reels, Stories",
        "  • YouTube — Videos, Shorts, Streams",
        "  • Pinterest — Video Pins",
        "",
        "Usage:",
        "  Just send the link!"
    ]
    return quoted_block("\n".join(lines))

def format_help_music() -> str:
    """Format music download help section"""
    lines = [
        "Music Download",
        "━" * 30,
        "",
        "Commands:",
        "  /mp3 [song name] — Search and download",
        "",
        "Spotify:",
        "  Send Spotify playlist URL",
        "  Songs sent to your DM",
        "  Real-time progress updates"
    ]
    return quoted_block("\n".join(lines))

def format_help_info() -> str:
    """Format info commands help section"""
    lines = [
        "Info Commands",
        "━" * 30,
        "",
        "  /id — Get user ID",
        "  /chatid — Get chat ID",
        "  /myinfo — Your full info"
    ]
    return quoted_block("\n".join(lines))

def format_help_admin() -> str:
    """Format admin commands help section"""
    lines = [
        "Admin Commands",
        "━" * 30,
        "",
        "User Management:",
        "  /promote — Make user admin",
        "  /demote — Remove admin",
        "  /mute [min] — Mute user",
        "  /unmute — Unmute user",
        "  /ban — Ban user",
        "  /unban — Unban user"
    ]
    return quoted_block("\n".join(lines))

def format_help_filters() -> str:
    """Format filter commands help section"""
    lines = [
        "Filter Commands",
        "━" * 30,
        "",
        "Word Filtering:",
        "  /filter <word> — Filter word",
        "  /unfilter <word> — Remove filter",
        "  /filters — List all filters",
        "",
        "Exact Blocking:",
        "  /block <word> — Block exact word",
        "  /unblock <word> — Unblock word",
        "  /blocklist — List blocked words",
        "",
        "Other:",
        "  /whisper <msg> — Private message"
    ]
    return quoted_block("\n".join(lines))
