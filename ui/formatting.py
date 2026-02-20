"""
NAGU DOWNLOADER — UI Formatting System
Clean • Modern • Telegram Native

Design principles:
  - Plain HTML messages — no monospace panels for user-facing messages
  - Minimal captions — no debug, no timing, no platform info
  - Quote original message on every reply
  - Mention user on delivery
  - All parse_mode = HTML
"""
from __future__ import annotations
from typing import List
from aiogram.types import User


# ─── Core primitives ──────────────────────────────────────────────────────────

def mention(user: User) -> str:
    """Clickable HTML user mention"""
    if not user:
        return "Unknown"
    name = (user.first_name or "User")[:32]
    safe = name.replace("<", "").replace(">", "")
    return f'<a href="tg://user?id={user.id}">{safe}</a>'


def format_delivered_with_mention(user_id: int, first_name: str) -> str:
    """
    Returns a clean delivered message with clickable user mention.
    Uses HTML mode for safety.

    Output: ✓ Delivered — <Name>
    """
    safe_name = (first_name or "User")[:32].replace("<", "").replace(">", "")
    return f'✓ Delivered — <a href="tg://user?id={user_id}">{safe_name}</a>'


def format_user_id(user_id: int) -> str:
    """Monospace user ID"""
    return f"<code>{user_id}</code>"


def mono(text: str) -> str:
    """Wrap in monospace code block"""
    return f"<code>{text}</code>"


def bold(text: str) -> str:
    """Bold text"""
    return f"<b>{text}</b>"


def quoted_block(content: str) -> str:
    """Telegram expandable quote block — legacy compat"""
    return f"<blockquote>{content}</blockquote>"


def styled_text(text: str) -> str:
    """Legacy compat — returns text as-is"""
    return text


def premium_panel(title: str, lines: list) -> str:
    """Legacy compat — builds a quoted panel"""
    content = f"{title}\n{'─' * 28}\n" + "\n".join(lines)
    return quoted_block(content)


def format_downloading() -> str:
    """Legacy compat"""
    return "⏳ Processing link..."


def code_panel(lines: List[str], width: int = 32) -> str:
    """Monospace panel wrapped in <code> block — used for /id, /chatid, /myinfo"""
    top    = f"╔{'═' * width}╗"
    mid    = f"╠{'═' * width}╣"
    bottom = f"╚{'═' * width}╝"

    def row(text: str) -> str:
        text = text[:width]
        pad = width - len(text)
        return f"║ {text}{' ' * (pad - 1)}║"

    result = [top]
    for line in lines:
        if line == "---":
            result.append(mid)
        else:
            result.append(row(line))
    result.append(bottom)
    return f"<code>{chr(10).join(result)}</code>"


# ─── /start ───────────────────────────────────────────────────────────────────

def format_welcome(user: User, user_id: int) -> str:
    """
    👋 Welcome to Nagu Downloader

    Send a link from:
    • YouTube
    • Instagram
    • Spotify
    • Pinterest

    Fast. Clean. Delivered.
    """
    return (
        "👋 <b>Welcome to Nagu Downloader</b>\n\n"
        "Send a link from:\n"
        "• YouTube\n"
        "• Instagram\n"
        "• Spotify\n"
        "• Pinterest\n\n"
        "Fast. Clean. Delivered."
    )


# ─── /help ────────────────────────────────────────────────────────────────────

def format_help_video() -> str:
    return (
        "🎬 <b>Video Download</b>\n\n"
        "Instagram  — Reels / Posts\n"
        "YouTube    — Videos / Shorts\n"
        "Pinterest  — Video Pins\n\n"
        "Just send the link."
    )


def format_help_music() -> str:
    return (
        "🎵 <b>Music Download</b>\n\n"
        "Spotify   — Single track\n"
        "Spotify   — Playlist (sent to DM)\n"
        "YT Music  — 320kbps audio\n\n"
        "Playlist songs are delivered to your DM."
    )


def format_help_info() -> str:
    return (
        "ℹ <b>Bot Commands</b>\n\n"
        "/id       — your user ID\n"
        "/chatid   — current chat ID\n"
        "/myinfo   — account details\n"
        "/broadcast — admin only"
    )


# ─── /myinfo ──────────────────────────────────────────────────────────────────

def format_myinfo(user: User, chat_title: str = None) -> str:
    username = f"@{user.username}" if user.username else "—"
    lines = [
        "  MY  INFO",
        "---",
        f"  Name  ·  {(user.first_name or '')[:20]}",
        f"  Last  ·  {(user.last_name or '—')[:20]}",
        f"  User  ·  {username[:20]}",
        f"  ID    ·  {user.id}",
        f"  Lang  ·  {user.language_code or '—'}",
    ]
    if chat_title:
        lines += ["---", f"  Chat  ·  {chat_title[:20]}"]
    return code_panel(lines, width=32)


# ─── /id ──────────────────────────────────────────────────────────────────────

def format_id(user: User, label: str = "YOUR  ID") -> str:
    username = f"@{user.username}" if user.username else "—"
    lines = [
        f"  {label}",
        "---",
        f"  Name  ·  {(user.first_name or '')[:20]}",
        f"  User  ·  {username}",
        f"  ID    ·  {user.id}",
    ]
    return code_panel(lines, width=32)


# ─── /chatid ──────────────────────────────────────────────────────────────────

def format_chatid(chat_id: int, chat_title: str, chat_type: str) -> str:
    lines = [
        "  CHAT  ID",
        "---",
        f"  Chat  ·  {chat_title[:20]}",
        f"  Type  ·  {chat_type}",
        f"  ID    ·  {chat_id}",
    ]
    return code_panel(lines, width=32)


# ─── Admin panel ──────────────────────────────────────────────────────────────

def format_admin_panel(stats: dict = None) -> str:
    lines = [
        "  ADMIN  PANEL",
        "---",
        "  /broadcast <msg>",
        "  /broadcast_media",
        "  /stats",
        "---",
    ]
    if stats:
        lines += [
            f"  Users   ·  {stats.get('users', 0)}",
            f"  Groups  ·  {stats.get('groups', 0)}",
        ]
    return code_panel(lines, width=32)


# ─── /status ──────────────────────────────────────────────────────────────────

def format_status(active_jobs: int = 0, queue: int = 0, uptime: str = "—") -> str:
    return (
        f"📊 <b>Bot Status</b>\n\n"
        f"Active Jobs: {active_jobs}\n"
        f"Queue: {queue}\n"
        f"Uptime: {uptime}"
    )


# ─── Download status messages ─────────────────────────────────────────────────

def format_processing(platform: str = "") -> str:
    """Initial processing message"""
    if platform == "youtube":
        return "⏳ Processing link..."
    elif platform == "shorts":
        return "⚡ Processing Short..."
    elif platform == "ytmusic":
        return "🎵 Processing Audio..."
    elif platform == "instagram":
        return "⚡ Fetching Media..."
    elif platform == "pinterest":
        return "📌 Fetching Media..."
    elif platform == "spotify":
        return "🎵 Processing Track..."
    return "⏳ Processing link..."


def format_progress(pct: int, label: str = "Preparing media...") -> str:
    """
    📥 Downloading

    [████░░░░░░] 40%
    Preparing media...
    """
    width = 10
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"📥 <b>Downloading</b>\n\n[{bar}] {pct}%\n{label}"


def format_delivered() -> str:
    """Plain delivery confirmation"""
    return "✓ Delivered"


def format_error(message: str | None = None) -> str:
    """Global error message — never show debug info"""
    return "⚠ Unable to process this link.\n\nPlease try again."


# ─── Spotify progress ─────────────────────────────────────────────────────────

def format_playlist_detected() -> str:
    return "🎵 <b>Playlist Detected</b>\n\nStarting download..."


def format_playlist_progress(name: str, done: int, total: int) -> str:
    """
    Playlist: {name}

    [██████░░░░] 60%
    420 / 700 completed
    """
    if total > 0:
        pct = min(100, int(done * 100 / total))
    else:
        pct = 0
    width = 10
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    name_short = (name or "Playlist")[:30]
    return (
        f"Playlist: {name_short}\n\n"
        f"[{bar}] {pct}%\n"
        f"{done} / {total} completed"
    )


def format_playlist_final(user: User, name: str, total: int, sent: int, failed: int) -> str:
    """
    🎉 Playlist Completed — mention

    Total: 700
    Sent: 692
    Failed: 8
    """
    safe_name = (user.first_name or "User")[:32].replace("<", "").replace(">", "")
    user_link = f'<a href="tg://user?id={user.id}">{safe_name}</a>'
    return (
        f"🎉 <b>Playlist Completed</b>\n\n"
        f"Total: {total}\n"
        f"Sent: {sent}\n"
        f"Failed: {failed}\n\n"
        f"{user_link}"
    )


def format_playlist_dm_complete(name: str) -> str:
    """Final DM message after playlist delivery"""
    return (
        "🎵 <b>Playlist Delivered</b>\n\n"
        "Thank you for using Nagu Downloader."
    )


def format_spotify_complete(user: User, total: int, sent: int) -> str:
    """Legacy compat"""
    return format_playlist_final(user, "", total, sent, total - sent)


# ─── Broadcast ────────────────────────────────────────────────────────────────

def format_broadcast_started() -> str:
    return "📢 <b>Broadcast Started</b>"


def format_broadcast_report(total_users: int, total_groups: int, success: int, failed: int) -> str:
    return (
        f"📢 <b>Broadcast Report</b>\n\n"
        f"Users: {total_users:,}\n"
        f"Groups: {total_groups:,}\n"
        f"Success: {success:,}\n"
        f"Failed: {failed:,}"
    )


# ─── Legacy compat ────────────────────────────────────────────────────────────

def format_welcome_legacy(user: User, user_id: int) -> str:
    return format_welcome(user, user_id)


def format_help_video_legacy() -> str:
    return format_help_video()


def format_help_music_legacy() -> str:
    return format_help_music()


def format_help_info_legacy() -> str:
    return format_help_info()


def format_download_complete(user: User, elapsed: float, platform: str) -> str:
    """Legacy compat"""
    return format_delivered()


def format_audio_info(user: User, title: str, artist: str, size_mb: float, elapsed: float) -> str:
    """Legacy compat"""
    return format_delivered()


def format_user_info(user: User, chat_title: str = None) -> str:
    return format_myinfo(user, chat_title)
