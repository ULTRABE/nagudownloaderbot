"""
NAGU DOWNLOADER — UI Formatting System
Clean • Modern • Telegram Native

Design principles:
  - Plain HTML messages — no monospace panels for user-facing messages
  - Minimal captions — no debug, no timing, no platform info
  - Quote original message on every reply
  - Mention user on delivery
  - All parse_mode = HTML
  - Unified Unicode bold/small-caps font for ALL static headings
  - Dynamic values (numbers, percentages, mentions, URLs) stay plain

Font style reference:
  𝐒ᴛʏʟᴇᴅ 𝐇𝐞𝐚𝐝𝐢𝐧𝐠
  𝟦𝟢–𝟧𝟢 ᴍɪɴᴜᴛᴇꜱ+ ꜰᴀꜱᴛᴇʀ ᴅᴏᴡɴʟᴏᴀᴅꜱ
  ꜱᴍᴏᴏᴛʜ ᴇxᴘᴇʀɪᴇɴᴄᴇ
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
    Welcome message with unified font heading and special footer lines.
    """
    return (
        "👋 <b>𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐭𝐨 𝐍𝐚𝐠𝐮 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫</b>\n\n"
        "ꜱᴇɴᴅ ᴀ ʟɪɴᴋ ꜰʀᴏᴍ:\n"
        "• YouTube\n"
        "• Instagram\n"
        "• Spotify\n"
        "• Pinterest\n\n"
        "𝟦𝟢–𝟧𝟢 ᴍɪɴᴜᴛᴇꜱ+ ꜰᴀꜱᴛᴇʀ ᴅᴏᴡɴʟᴏᴀᴅꜱ\n"
        "ꜱᴍᴏᴏᴛʜ ᴇxᴘᴇʀɪᴇɴᴄᴇ"
    )


# ─── /help ────────────────────────────────────────────────────────────────────

def format_help() -> str:
    """Single unified help message with stylized heading"""
    return (
        "𝐇𝐞𝐥𝐩 — 𝐂𝐨𝐦𝐦𝐚𝐧𝐝𝐬 &amp; 𝐅𝐞𝐚𝐭𝐮𝐫𝐞𝐬\n\n"
        "/start — Start the bot\n"
        "/help — Show commands\n"
        "/id — Get your user ID\n"
        "/chatid — Get chat ID\n"
        "/myinfo — Account details\n"
        "/broadcast — Admin broadcast\n"
        "/mp3 — Extract audio from video\n\n"
        "<b>𝐅𝐞𝐚𝐭𝐮𝐫𝐞𝐬:</b>\n\n"
        "• YouTube — Video / Audio download\n"
        "• Spotify — Track &amp; playlist support\n"
        "• Instagram — Reels &amp; posts\n"
        "• Pinterest — Video pins\n"
        "• Fast progress bar system"
    )


# Legacy compat — keep old functions pointing to new single help
def format_help_video() -> str:
    return format_help()


def format_help_music() -> str:
    return ""


def format_help_info() -> str:
    return ""


# ─── /myinfo ──────────────────────────────────────────────────────────────────

def format_myinfo(user: User, chat_title: str = None) -> str:
    """Clean plain HTML — stylized heading"""
    username = f"@{user.username}" if user.username else "—"
    chat_type = "private" if not chat_title else "group"
    text = (
        "👤 <b>𝐀𝐜𝐜𝐨𝐮𝐧𝐭 𝐈𝐧𝐟𝐨</b>\n\n"
        f"Name: {(user.first_name or '—')[:32]}\n"
        f"Last Name: {(user.last_name or '—')[:32]}\n"
        f"Username: {username}\n"
        f"User ID: <code>{user.id}</code>\n"
        f"Language: {user.language_code or '—'}\n"
        f"Chat Type: {chat_type}"
    )
    return text


# ─── /id ──────────────────────────────────────────────────────────────────────

def format_id(user: User, label: str = "YOUR  ID") -> str:
    """Clean plain HTML — stylized heading"""
    username = f"@{user.username}" if user.username else "—"
    is_other = "USER" in label.upper()
    title = "🆔 𝐔𝐬𝐞𝐫 𝐈𝐃" if is_other else "🆔 𝐘𝐨𝐮𝐫 𝐈𝐃"
    return (
        f"{title}\n\n"
        f"Name: {(user.first_name or '—')[:32]}\n"
        f"Username: {username}\n"
        f"User ID: <code>{user.id}</code>"
    )


# ─── /chatid ──────────────────────────────────────────────────────────────────

def format_chatid(chat_id: int, chat_title: str, chat_type: str) -> str:
    """Clean plain HTML — stylized heading"""
    return (
        "💬 <b>𝐂𝐡𝐚𝐭 𝐈𝐃</b>\n\n"
        f"Chat: {chat_title[:32]}\n"
        f"Type: {chat_type}\n"
        f"ID: <code>{chat_id}</code>"
    )


# ─── Admin panel ──────────────────────────────────────────────────────────────

def format_admin_panel(stats: dict = None) -> str:
    """Clean plain HTML admin panel — stylized heading"""
    text = (
        "🔧 <b>𝐀𝐝𝐦𝐢𝐧 𝐏𝐚𝐧𝐞𝐥</b>\n\n"
        "/broadcast &lt;msg&gt; — send to all\n"
        "/broadcast_media — reply to media\n"
        "/assign — configure emoji/stickers\n"
        "/stats — user/group counts\n"
    )
    if stats:
        text += (
            f"\nUsers: {stats.get('users', 0)}\n"
            f"Groups: {stats.get('groups', 0)}"
        )
    return text


# ─── /status ──────────────────────────────────────────────────────────────────

def format_status(active_jobs: int = 0, queue: int = 0, uptime: str = "—") -> str:
    return (
        f"📊 <b>𝐁𝐨𝐭 𝐒𝐭𝐚𝐭𝐮𝐬</b>\n\n"
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
    📥 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐢𝐧𝐠

    [████░░░░░░] 40%
    Preparing media...
    """
    width = 10
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"📥 <b>𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐢𝐧𝐠</b>\n\n[{bar}] {pct}%\n{label}"


def format_delivered() -> str:
    """Plain delivery confirmation"""
    return "✓ Delivered"


def format_error(message: str | None = None) -> str:
    """Global error message — never show debug info"""
    return "⚠ Unable to process this link.\n\nPlease try again."


# ─── Spotify progress ─────────────────────────────────────────────────────────

def format_playlist_detected() -> str:
    return "🎵 <b>𝐏ʟᴀʏʟɪꜱᴛ 𝐃𝐞𝐭𝐞𝐜𝐭𝐞𝐝</b>\n\nStarting download..."


def format_playlist_progress(name: str, done: int, total: int) -> str:
    """
    𝐏ʟᴀʏʟɪꜱᴛ: {name}

    [██████░░░░] 60%
    420 / 700
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
        f"𝐏ʟᴀʏʟɪꜱᴛ: {name_short}\n\n"
        f"[{bar}] {pct}%\n"
        f"{done} / {total}"
    )


def format_playlist_final(user: User, name: str, total: int, sent: int, failed: int) -> str:
    """
    𝐏ʟᴀʏʟɪꜱᴛ 𝐂ᴏᴍᴘʟᴇᴛᴇᴅ

    Total: 700
    Sent: 692
    Failed: 8
    """
    safe_name = (user.first_name or "User")[:32].replace("<", "").replace(">", "")
    user_link = f'<a href="tg://user?id={user.id}">{safe_name}</a>'
    return (
        f"𝐏ʟᴀʏʟɪꜱᴛ 𝐂ᴏᴍᴘʟᴇᴛᴇᴅ\n\n"
        f"Total: {total}\n"
        f"Sent: {sent}\n"
        f"Failed: {failed}\n\n"
        f"{user_link}"
    )


def format_playlist_dm_complete(name: str) -> str:
    """Final DM message after playlist delivery"""
    return "𝐏ʟᴀʏʟɪꜱᴛ 𝐃𝐞𝐥𝐢𝐯𝐞𝐫𝐞𝐝."


def format_spotify_complete(user: User, total: int, sent: int) -> str:
    """Legacy compat"""
    return format_playlist_final(user, "", total, sent, total - sent)


# ─── YouTube playlist ─────────────────────────────────────────────────────────

def format_yt_playlist_mode(playlist_name: str) -> str:
    """Mode selection for YouTube playlist"""
    name_short = (playlist_name or "Playlist")[:40]
    return f"𝐏ʟᴀʏʟɪꜱᴛ: {name_short}\n\nChoose Download Mode:"


def format_yt_audio_quality() -> str:
    """Audio quality selection"""
    return "𝐀ᴜᴅɪᴏ 𝐐ᴜᴀʟɪᴛʏ"


def format_yt_video_quality() -> str:
    """Video quality selection"""
    return "𝐕ɪᴅᴇᴏ 𝐐ᴜᴀʟɪᴛʏ"


def format_yt_playlist_progress(name: str, done: int, total: int) -> str:
    """YouTube playlist progress bar"""
    if total > 0:
        pct = min(100, int(done * 100 / total))
    else:
        pct = 0
    width = 10
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    name_short = (name or "Playlist")[:30]
    return (
        f"𝐏ʟᴀʏʟɪꜱᴛ: {name_short}\n\n"
        f"[{bar}] {pct}%\n"
        f"{done} / {total}"
    )


def format_yt_playlist_final(name: str, total: int, sent: int, failed: int) -> str:
    """YouTube playlist completion message"""
    name_short = (name or "Playlist")[:30]
    return (
        f"𝐏ʟᴀʏʟɪꜱᴛ 𝐂ᴏᴍᴘʟᴇᴛᴇᴅ\n\n"
        f"Total: {total}\n"
        f"Sent: {sent}\n"
        f"Failed: {failed}"
    )


# ─── Broadcast ────────────────────────────────────────────────────────────────

def format_broadcast_started() -> str:
    return "📢 <b>𝐁ʀᴏᴀᴅᴄᴀꜱᴛ 𝐒𝐭𝐚𝐫𝐭𝐞𝐝</b>"


def format_broadcast_report(total_users: int, total_groups: int, success: int, failed: int) -> str:
    return (
        f"📢 <b>𝐁ʀᴏᴀᴅᴄᴀꜱᴛ 𝐑𝐞𝐩𝐨𝐫𝐭</b>\n\n"
        f"Users: {total_users:,}\n"
        f"Groups: {total_groups:,}\n"
        f"Success: {success:,}\n"
        f"Failed: {failed:,}"
    )


# ─── Emoji assign system ──────────────────────────────────────────────────────

# Emoji position definitions: internal_key → display_label
EMOJI_POSITIONS = {
    "DELIVERED":  "✓ Delivered",
    "ERROR":      "⚠ Error",
    "MUSIC":      "🎵 Music",
    "BROADCAST":  "📢 Broadcast",
    "PINTEREST":  "📌 Pinterest",
    "YOUTUBE":    "🎬 YouTube",
    "INSTAGRAM":  "📸 Instagram",
    "SPOTIFY":    "🎧 Spotify",
}


def format_assign_menu(configured_keys: set) -> str:
    """
    𝐄ᴍᴏᴊɪ 𝐒𝐞𝐭𝐮𝐩

    Display rows with configured/not-configured status.
    """
    lines = ["𝐄ᴍᴏᴊɪ 𝐒𝐞𝐭𝐮𝐩\n"]
    for key, label in EMOJI_POSITIONS.items():
        status = "[Configured]" if key in configured_keys else "[Not set]"
        lines.append(f"{label}  →  {status}")
    return "\n".join(lines)


def format_assign_prompt(label: str) -> str:
    """Prompt admin to send sticker for a position"""
    return (
        f"𝐒𝐞𝐭 𝐄ᴍᴏᴊɪ\n\n"
        f"Send the sticker to use for:\n"
        f"<b>{label}</b>"
    )


def format_assign_updated() -> str:
    return "𝐄ᴍᴏᴊɪ 𝐔ᴘᴅᴀᴛᴇᴅ ✓"


# ─── Stats ────────────────────────────────────────────────────────────────────

def format_stats(users: int, groups: int) -> str:
    return (
        f"📊 <b>𝐁𝐨𝐭 𝐒𝐭𝐚𝐭𝐬</b>\n\n"
        f"Users: {users}\n"
        f"Groups: {groups}"
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
