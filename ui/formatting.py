"""
╔══════════════════════════════════════════════════════════╗
║         NAGU BOT — Premium Monospace UI System           ║
║         Symmetrical · Clean · Minimal · Fast             ║
╚══════════════════════════════════════════════════════════╝

Design principles:
  - Monospace code blocks for all structured data
  - Symmetrical borders using box-drawing characters
  - Minimal captions — no debug, no timing, no platform info
  - Quote original message on every reply
  - Premium emoji support via config
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
    return f'<a href="tg://user?id={user.id}">{name}</a>'

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
    """Telegram expandable quote block"""
    return f"<blockquote>{content}</blockquote>"

def styled_text(text: str) -> str:
    """
    Convert text to styled Unicode small-caps font.
    Used for section headers and labels.
    """
    bold_map = {
        'A': '𝗔', 'B': '𝗕', 'C': '𝗖', 'D': '𝗗', 'E': '𝗘', 'F': '𝗙', 'G': '𝗚', 'H': '𝗛',
        'I': '𝗜', 'J': '𝗝', 'K': '𝗞', 'L': '𝗟', 'M': '𝗠', 'N': '𝗡', 'O': '𝗢', 'P': '𝗣',
        'Q': '𝗤', 'R': '𝗥', 'S': '𝗦', 'T': '𝗧', 'U': '𝗨', 'V': '𝗩', 'W': '𝗪', 'X': '𝗫',
        'Y': '𝗬', 'Z': '𝗭',
    }
    small_caps = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ', 'g': 'ɢ', 'h': 'ʜ',
        'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ',
        'q': 'ǫ', 'r': 'ʀ', 's': 'ꜱ', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x',
        'y': 'ʏ', 'z': 'ᴢ',
    }
    return ''.join(bold_map.get(c) or small_caps.get(c) or c for c in text)


# ─── Panel builder ────────────────────────────────────────────────────────────

def panel(lines: List[str], width: int = 32) -> str:
    """
    Build a symmetrical monospace panel.

    ╔══════════════════════════════╗
    ║  TITLE                       ║
    ╠══════════════════════════════╣
    ║  key  ·  value               ║
    ╚══════════════════════════════╝
    """
    top    = f"╔{'═' * width}╗"
    mid    = f"╠{'═' * width}╣"
    bottom = f"╚{'═' * width}╝"

    def row(text: str) -> str:
        # Pad to width, truncate if needed
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
    return "<code>" + "\n".join(result) + "</code>"


def _panel_raw(lines: List[str], width: int = 32) -> str:
    """Build panel as plain text (for use inside <code> blocks)"""
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
    return "\n".join(result)


def code_panel(lines: List[str], width: int = 32) -> str:
    """Monospace panel wrapped in <code> block"""
    return f"<code>{_panel_raw(lines, width)}</code>"


def premium_panel(title: str, lines: list) -> str:
    """Legacy compat — builds a quoted panel"""
    content = f"{title}\n{'─' * 28}\n" + "\n".join(lines)
    return quoted_block(content)


# ─── Welcome / Start ──────────────────────────────────────────────────────────

def format_welcome(user: User, user_id: int) -> str:
    """
    Welcome message — symmetrical monospace panel.

    ╔══════════════════════════════╗
    ║  NAGU DOWNLOADER             ║
    ╠══════════════════════════════╣
    ║  Name  ·  John               ║
    ║  ID    ·  123456789          ║
    ╠══════════════════════════════╣
    ║  /help  ·  commands          ║
    ║  Send any link to download   ║
    ╚══════════════════════════════╝
    """
    username = f"@{user.username}" if user.username else "—"
    name = (user.first_name or "User")[:20]

    lines = [
        "  NAGU  DOWNLOADER  BOT",
        "---",
        f"  Name  ·  {name}",
        f"  User  ·  {username}",
        f"  ID    ·  {user_id}",
        "---",
        "  /help  ·  all commands",
        "  Send any link to start",
        "---",
        "  Owner  ·  @bhosadih",
    ]
    return code_panel(lines, width=32)


# ─── Help panels ──────────────────────────────────────────────────────────────

def format_help_video() -> str:
    lines = [
        "  VIDEO  DOWNLOAD",
        "---",
        "  Instagram  ·  Reels / Posts",
        "  YouTube    ·  Videos / Shorts",
        "  Pinterest  ·  Video Pins",
        "---",
        "  Just send the link",
    ]
    return code_panel(lines, width=32)


def format_help_music() -> str:
    lines = [
        "  MUSIC  DOWNLOAD",
        "---",
        "  Spotify  ·  Single track",
        "  Spotify  ·  Playlist (groups)",
        "  YT Music ·  320kbps audio",
        "---",
        "  Playlist → songs to DM",
    ]
    return code_panel(lines, width=32)


def format_help_info() -> str:
    lines = [
        "  INFO  COMMANDS",
        "---",
        "  /id      ·  your user ID",
        "  /chatid  ·  chat ID",
        "  /myinfo  ·  full details",
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


# ─── Download status messages ─────────────────────────────────────────────────

def format_downloading() -> str:
    """Initial 'downloading' status"""
    return mono("  ⬇  Downloading...")


def format_progress(pct: int, label: str = "") -> str:
    """
    Dynamic progress bar.
    [▓▓▓▓▓░░░░░]  50%
    """
    width = 10
    filled = int(width * pct / 100)
    bar = "▓" * filled + "░" * (width - filled)
    line = f"  [{bar}]  {pct}%"
    if label:
        line += f"  {label}"
    return mono(line)


def format_delivered() -> str:
    """Minimal delivery confirmation — reply to original"""
    return "✓ Delivered"


def format_error(message: str | None = None) -> str:
    """Error message with optional detail"""
    base = "⚠ Unable to process this link."
    if message:
        return f"{base}\n\n{message}"
    return base


def format_processing(text: str = "Processing...") -> str:
    """Generic processing status"""
    return f"⏳ {text}"


def format_spotify_complete(user: User, total: int, sent: int) -> str:
    """Spotify playlist completion — mention user"""
    return (
        f"{mention(user)}\n"
        f"{mono(f'  Playlist  ·  {sent}/{total} sent')}"
    )


# ─── Spotify progress (group chat) ───────────────────────────────────────────

def format_playlist_progress(name: str, done: int, total: int) -> str:
    """
    Monospace playlist progress for group chat.

    ╔══════════════════════════════╗
    ║  Playlist: NAME              ║
    ╠══════════════════════════════╣
    ║  [▓▓▓▓░░░░░░]  40%           ║
    ║  280 / 700  completed        ║
    ╚══════════════════════════════╝
    """
    if total > 0:
        pct = min(100, int(done * 100 / total))
    else:
        pct = 0
    width = 10
    filled = int(width * pct / 100)
    bar = "▓" * filled + "░" * (width - filled)
    name_short = name[:22] if name else "Playlist"

    lines = [
        f"  Playlist: {name_short}",
        "---",
        f"  [{bar}]  {pct}%",
        f"  {done} / {total}  completed",
    ]
    return code_panel(lines, width=32)


def format_playlist_final(user: User, name: str, total: int, sent: int, failed: int) -> str:
    """
    Final group chat summary after playlist completes.
    """
    lines = [
        "  PLAYLIST  COMPLETE",
        "---",
        f"  Name    ·  {name[:20]}",
        f"  Total   ·  {total}",
        f"  Sent    ·  {sent}",
        f"  Failed  ·  {failed}",
    ]
    return f"{mention(user)}\n{code_panel(lines, width=32)}"


def format_playlist_dm_complete(name: str) -> str:
    """Final DM message after playlist delivery"""
    lines = [
        "  PLAYLIST  DELIVERED",
        "---",
        f"  {name[:28]}",
        "---",
        "  Status  ·  Completed",
        "  Thank you for using",
        "  IDIRECTNango Downloader",
    ]
    return code_panel(lines, width=32)


# ─── Broadcast report ─────────────────────────────────────────────────────────

def format_broadcast_report(total_users: int, total_groups: int, success: int, failed: int) -> str:
    lines = [
        "  BROADCAST  REPORT",
        "---",
        f"  Users    ·  {total_users}",
        f"  Groups   ·  {total_groups}",
        f"  Success  ·  {success}",
        f"  Failed   ·  {failed}",
    ]
    return code_panel(lines, width=32)


# ─── User info panels ─────────────────────────────────────────────────────────

def format_user_info(user: User, chat_title: str = None) -> str:
    username = f"@{user.username}" if user.username else "—"
    lines = [
        "  USER  INFO",
        "---",
        f"  Name  ·  {(user.first_name or '')[:20]}",
        f"  User  ·  {username[:20]}",
        f"  ID    ·  {user.id}",
    ]
    if chat_title:
        lines += ["---", f"  Chat  ·  {chat_title[:20]}"]
    return code_panel(lines, width=32)


def format_download_complete(user: User, elapsed: float, platform: str) -> str:
    """Legacy compat — minimal caption"""
    return format_delivered()


def format_audio_info(user: User, title: str, artist: str, size_mb: float, elapsed: float) -> str:
    """Legacy compat"""
    return format_delivered()
