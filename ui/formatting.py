"""
NAGU DOWNLOADER — UI Formatting System
Clean • Modern • Telegram Native

Design principles:
  - Plain HTML messages — no monospace panels for user-facing messages
  - Minimal captions — no debug, no timing, no platform info
  - Quote original message on every reply
  - Mention user on delivery
  - All parse_mode = HTML
  - Unified Unicode bold/small-caps font for ALL static headings via ui_title()
  - Dynamic values (numbers, percentages, mentions, URLs) stay plain

STRICT RULES:
  - Do NOT stylize: progress bars, percentages, dynamic numbers, file sizes,
    mentions, URLs, inline buttons
  - No duplicate stylizing, no double wrapping

Emoji usage:
  - All user-facing emojis come from get_emoji_async() (async functions)
  - Sync functions use get_emoji() as fallback (no Redis)
  - Never hardcode emojis in message strings — always use the emoji resolver
"""
from __future__ import annotations
from typing import List
from aiogram.types import User

from ui.emoji_config import get_emoji, get_emoji_async


# ─── Centralized UI title helper ──────────────────────────────────────────────

def ui_title(text: str) -> str:
    """
    Return a stylized heading string.

    Apply to: all headings, section headers, broadcast titles, error titles,
    playlist headers, completion headers, help header, start header.

    Do NOT apply to: progress bars, percentages, dynamic numbers, file sizes,
    mentions, URLs, inline buttons.

    The text is wrapped in <b> for Telegram HTML bold.
    Callers that already embed Unicode bold characters may pass them directly.
    """
    return f"<b>{text}</b>"


# ─── Core primitives ──────────────────────────────────────────────────────────

def mention(user: User) -> str:
    """Clickable HTML user mention"""
    if not user:
        return "Unknown"
    name = (user.first_name or "User")[:32]
    safe = name.replace("<", "").replace(">", "")
    return f'<a href="tg://user?id={user.id}">{safe}</a>'


async def format_delivered_with_mention(user_id: int, first_name: str) -> str:
    """
    Returns a clean delivered message with clickable user mention.
    Uses HTML mode for safety.

    Output: ✓ Delivered — <Name>
    """
    emoji = await get_emoji_async("DELIVERED")
    safe_name = (first_name or "User")[:32].replace("<", "").replace(">", "")
    return f'{emoji} Delivered — <a href="tg://user?id={user_id}">{safe_name}</a>'


def format_delivered_with_mention_sync(user_id: int, first_name: str) -> str:
    """
    Sync fallback for format_delivered_with_mention.
    Uses static emoji config (no Redis).
    """
    emoji = get_emoji("DELIVERED")
    safe_name = (first_name or "User")[:32].replace("<", "").replace(">", "")
    return f'{emoji} Delivered — <a href="tg://user?id={user_id}">{safe_name}</a>'


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


async def format_downloading() -> str:
    """Processing/downloading indicator"""
    emoji = await get_emoji_async("PROCESS")
    return f"{emoji} Processing link..."


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

async def format_welcome(user: User, user_id: int) -> str:
    """
    Welcome message with unified font heading.
    No promotional/marketing text.
    """
    wave = await get_emoji_async("WAVE")
    return (
        f"{wave} <b>𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐭𝐨 𝐍𝐚𝐠𝐮 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫</b>\n\n"
        "ꜱᴇɴᴅ ᴀ ʟɪɴᴋ ꜰʀᴏᴍ:\n"
        "• YouTube\n"
        "• Instagram\n"
        "• Spotify\n"
        "• Pinterest"
    )


# ─── /help ────────────────────────────────────────────────────────────────────

async def format_help() -> str:
    """Single unified help message with stylized heading"""
    info = await get_emoji_async("INFO")
    yt   = await get_emoji_async("YT")
    sp   = await get_emoji_async("SPOTIFY")
    ig   = await get_emoji_async("INSTA")
    pin  = await get_emoji_async("PINTEREST")
    return (
        f"{info} 𝐇𝐞𝐥𝐩 — 𝐂𝐨𝐦𝐦𝐚𝐧𝐝𝐬 &amp; 𝐅𝐞𝐚𝐭𝐮𝐫𝐞𝐬\n\n"
        "/start — Start the bot\n"
        "/help — Show commands\n"
        "/id — Get your user ID\n"
        "/chatid — Get chat ID\n"
        "/myinfo — Account details\n"
        "/broadcast — Admin broadcast\n"
        "/mp3 — Extract audio from video\n\n"
        "<b>𝐅𝐞𝐚𝐭𝐮𝐫𝐞𝐬:</b>\n\n"
        f"• {yt} YouTube — Video / Audio download\n"
        f"• {sp} Spotify — Track &amp; playlist support\n"
        f"• {ig} Instagram — Reels &amp; posts\n"
        f"• {pin} Pinterest — Video pins\n"
        "• Fast progress bar system"
    )


# Legacy compat — keep old functions pointing to new single help
async def format_help_video() -> str:
    return await format_help()


def format_help_music() -> str:
    return ""


def format_help_info() -> str:
    return ""


# ─── /myinfo ──────────────────────────────────────────────────────────────────

async def format_myinfo(user: User, chat_title: str = None) -> str:
    """Clean plain HTML — stylized heading"""
    user_emoji = await get_emoji_async("USER")
    username = f"@{user.username}" if user.username else "—"
    chat_type = "private" if not chat_title else "group"
    text = (
        f"{user_emoji} <b>𝐀𝐜𝐜𝐨𝐮𝐧𝐭 𝐈𝐧𝐟𝐨</b>\n\n"
        f"Name: {(user.first_name or '—')[:32]}\n"
        f"Last Name: {(user.last_name or '—')[:32]}\n"
        f"Username: {username}\n"
        f"User ID: <code>{user.id}</code>\n"
        f"Language: {user.language_code or '—'}\n"
        f"Chat Type: {chat_type}"
    )
    return text


# ─── /id ──────────────────────────────────────────────────────────────────────

async def format_id(user: User, label: str = "YOUR  ID") -> str:
    """Clean plain HTML — stylized heading"""
    id_emoji = await get_emoji_async("ID")
    username = f"@{user.username}" if user.username else "—"
    is_other = "USER" in label.upper()
    title = f"{id_emoji} 𝐔𝐬𝐞𝐫 𝐈𝐃" if is_other else f"{id_emoji} 𝐘𝐨𝐮𝐫 𝐈𝐃"
    return (
        f"{title}\n\n"
        f"Name: {(user.first_name or '—')[:32]}\n"
        f"Username: {username}\n"
        f"User ID: <code>{user.id}</code>"
    )


# ─── /chatid ──────────────────────────────────────────────────────────────────

async def format_chatid(chat_id: int, chat_title: str, chat_type: str) -> str:
    """Clean plain HTML — stylized heading"""
    info = await get_emoji_async("INFO")
    return (
        f"{info} <b>𝐂𝐡𝐚𝐭 𝐈𝐃</b>\n\n"
        f"Chat: {chat_title[:32]}\n"
        f"Type: {chat_type}\n"
        f"ID: <code>{chat_id}</code>"
    )


# ─── Admin panel ──────────────────────────────────────────────────────────────

async def format_admin_panel(stats: dict = None) -> str:
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

async def format_status(active_jobs: int = 0, queue: int = 0, uptime: str = "—") -> str:
    info = await get_emoji_async("INFO")
    return (
        f"{info} <b>𝐁𝐨𝐭 𝐒𝐭𝐚𝐭𝐮𝐬</b>\n\n"
        f"Active Jobs: {active_jobs}\n"
        f"Queue: {queue}\n"
        f"Uptime: {uptime}"
    )


# ─── Download status messages ─────────────────────────────────────────────────

async def format_processing(platform: str = "") -> str:
    """Initial processing message"""
    process = await get_emoji_async("PROCESS")
    fast    = await get_emoji_async("FAST")
    music   = await get_emoji_async("MUSIC")
    pin     = await get_emoji_async("PIN")

    if platform == "youtube":
        return f"{process} Processing link..."
    elif platform == "shorts":
        return f"{fast} Processing Short..."
    elif platform == "ytmusic":
        return f"{music} Processing Audio..."
    elif platform == "instagram":
        return f"{fast} Fetching Media..."
    elif platform == "pinterest":
        return f"{pin} Fetching Media..."
    elif platform == "spotify":
        return f"{music} Processing Track..."
    return f"{process} Processing link..."


async def format_progress(pct: int, label: str = "Preparing media...") -> str:
    """
    📥 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐢𝐧𝐠

    [████░░░░░░] 40%
    Preparing media...
    """
    dl = await get_emoji_async("DOWNLOAD")
    fast = await get_emoji_async("FAST")
    width = 10
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"{dl} <b>𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐢𝐧𝐠</b>\n\n[{bar}] {pct}%\n{fast} {label}"


async def format_delivered() -> str:
    """Plain delivery confirmation"""
    emoji = await get_emoji_async("DELIVERED")
    complete = await get_emoji_async("COMPLETE")
    return f"{emoji} {complete} Delivered"


async def format_error(message: str | None = None) -> str:
    """Global error message — never show debug info"""
    emoji = await get_emoji_async("ERROR")
    return f"{emoji} Unable to process this link.\n\nPlease try again."


# ─── Spotify progress ─────────────────────────────────────────────────────────

async def format_playlist_detected() -> str:
    music = await get_emoji_async("MUSIC")
    sp = await get_emoji_async("SPOTIFY")
    return f"{sp} <b>𝐏ʟᴀʏʟɪꜱᴛ 𝐃𝐞𝐭𝐞𝐜𝐭𝐞𝐝</b>\n\n{music} Starting download..."


def format_playlist_progress(name: str, done: int, total: int) -> str:
    """
    🎧 𝐏ʟᴀʏʟɪꜱᴛ: {name}

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
        f"🎧 <b>𝐏ʟᴀʏʟɪꜱᴛ:</b> {name_short}\n\n"
        f"[{bar}] {pct}%\n"
        f"{done} / {total}"
    )


async def format_playlist_final(user: User, name: str, total: int, sent: int, failed: int) -> str:
    """
    𝐏ʟᴀʏʟɪꜱᴛ 𝐂𝐨𝐦𝐩𝐥𝐞𝐭𝐞𝐝

    Total: 700
    Sent: 692
    Failed: 8
    """
    complete = await get_emoji_async("COMPLETE")
    sp = await get_emoji_async("SPOTIFY")
    safe_name = (user.first_name or "User")[:32].replace("<", "").replace(">", "")
    user_link = f'<a href="tg://user?id={user.id}">{safe_name}</a>'
    name_short = (name or "Playlist")[:30]
    return (
        f"{complete} <b>𝐏ʟᴀʏʟɪꜱᴛ 𝐂𝐨𝐦𝐩𝐥𝐞𝐭𝐞𝐝</b>\n\n"
        f"{sp} <b>{name_short}</b>\n\n"
        f"Total: {total}\n"
        f"Sent: {sent}\n"
        f"Failed: {failed}\n\n"
        f"{user_link}"
    )


def format_playlist_dm_complete(name: str) -> str:
    """Final DM message after playlist delivery"""
    return "𝐏ʟᴀʏʟɪꜱᴛ 𝐃𝐞𝐥𝐢𝐯𝐞𝐫𝐞ᴅ."


async def format_spotify_complete(user: User, total: int, sent: int) -> str:
    """Legacy compat"""
    return await format_playlist_final(user, "", total, sent, total - sent)


# ─── YouTube playlist ─────────────────────────────────────────────────────────

def format_yt_playlist_mode(playlist_name: str) -> str:
    """Mode selection for YouTube playlist"""
    name_short = (playlist_name or "Playlist")[:40]
    return f"🎬 <b>𝐏ʟᴀʏʟɪꜱᴛ:</b> {name_short}\n\n<b>𝐂𝐡𝐨𝐨𝐬𝐞 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝 𝐌𝐨𝐝𝐞:</b>"


def format_yt_audio_quality() -> str:
    """Audio quality selection"""
    return "🎵 <b>𝐀𝐮𝐝𝐢𝐨 𝐐𝐮𝐚𝐥𝐢𝐭𝐲</b>\n\nChoose your preferred audio quality:"


def format_yt_video_quality() -> str:
    """Video quality selection"""
    return "🎥 <b>𝐕𝐢𝐝𝐞𝐨 𝐐𝐮𝐚𝐥𝐢𝐭𝐲</b>\n\nChoose your preferred video quality:"


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
        f"🎬 <b>𝐏ʟᴀʏʟɪꜱᴛ:</b> {name_short}\n\n"
        f"[{bar}] {pct}%\n"
        f"{done} / {total}"
    )


async def format_yt_playlist_final(name: str, total: int, sent: int, failed: int) -> str:
    """YouTube playlist completion message"""
    complete = await get_emoji_async("COMPLETE")
    yt = await get_emoji_async("YT")
    name_short = (name or "Playlist")[:30]
    return (
        f"{complete} <b>𝐏ʟᴀʏʟɪꜱᴛ 𝐂𝐨𝐦𝐩𝐥𝐞𝐭𝐞𝐝</b>\n\n"
        f"{yt} <b>{name_short}</b>\n\n"
        f"Total: {total}\n"
        f"Sent: {sent}\n"
        f"Failed: {failed}"
    )


# ─── Broadcast ────────────────────────────────────────────────────────────────

async def format_broadcast_started() -> str:
    bc = await get_emoji_async("BROADCAST")
    return f"{bc} <b>𝐁ʀᴏᴀᴅᴄᴀꜱᴛ 𝐒𝐭𝐚𝐫𝐭𝐞ᴅ</b>"


async def format_broadcast_report(total_users: int, total_groups: int, success: int, failed: int) -> str:
    bc = await get_emoji_async("BROADCAST")
    return (
        f"{bc} <b>𝐁ʀᴏᴀᴅᴄᴀꜱᴛ 𝐑𝐞𝐩𝐨𝐫𝐭</b>\n\n"
        f"Users: {total_users:,}\n"
        f"Groups: {total_groups:,}\n"
        f"Success: {success:,}\n"
        f"Failed: {failed:,}"
    )


# ─── Emoji assign system ──────────────────────────────────────────────────────

# Emoji position definitions: internal_key → display_label
# Covers ALL keys from core/emoji_config.py and ui/emoji_config.py
EMOJI_POSITIONS = {
    # Platform stickers
    "YOUTUBE":    "🎬 YouTube",
    "INSTAGRAM":  "📸 Instagram",
    "PINTEREST":  "📌 Pinterest",
    "MUSIC":      "🎵 Music",
    "VIDEO":      "🎥 Video",
    "SPOTIFY":    "🎧 Spotify",
    "PLAYLIST":   "🎶 Playlist",
    # Status indicators
    "DELIVERED":  "✓ Delivered",
    "SUCCESS":    "✅ Success",
    "ERROR":      "⚠ Error",
    "PROCESS":    "⏳ Processing",
    "FAST":       "⚡ Fast",
    "DOWNLOAD":   "📥 Download",
    "COMPLETE":   "🎉 Complete",
    "LOADING":    "⏳ Loading",
    "CHECK":      "✅ Check",
    # Commands / UI
    "BROADCAST":  "📢 Broadcast",
    "INFO":       "ℹ Info",
    "ID":         "🆔 ID",
    "USER":       "👤 User",
    "PING":       "🏓 Ping",
    "PIN":        "📌 Pin",
    # Decorative
    "STAR":       "⭐ Star",
    "FIRE":       "🔥 Fire",
    "ROCKET":     "🚀 Rocket",
    "CROWN":      "👑 Crown",
    "DIAMOND":    "💎 Diamond",
    "ZAP":        "⚡ Zap",
    "WAVE":       "👋 Wave",
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
    """Prompt admin to send a premium emoji or unicode emoji for a position"""
    return (
        f"𝐒𝐞𝐭 𝐄ᴍᴏᴊɪ\n\n"
        f"Send a premium emoji (custom emoji) or a standard emoji for:\n"
        f"<b>{label}</b>\n\n"
        f"<i>Tip: Send a message containing a Telegram premium custom emoji, "
        f"or just type a regular emoji like 🎵</i>"
    )


def format_assign_updated() -> str:
    return "𝐄ᴍᴏᴊɪ 𝐔ᴘᴅᴀᴛᴇᴅ ✓"


# ─── Stats ────────────────────────────────────────────────────────────────────

async def format_stats(users: int, groups: int) -> str:
    info = await get_emoji_async("INFO")
    return (
        f"{info} <b>𝐁𝐨𝐭 𝐒𝐭𝐚𝐭𝐬</b>\n\n"
        f"Users: {users}\n"
        f"Groups: {groups}"
    )


# ─── Legacy compat ────────────────────────────────────────────────────────────

async def format_user_info(user: User) -> str:
    """Legacy compat — returns user info panel (same as format_myinfo)"""
    return await format_myinfo(user)


async def format_download_complete(user: User) -> str:
    """Legacy compat — returns a delivered confirmation with mention"""
    emoji = await get_emoji_async("DELIVERED")
    safe_name = (user.first_name or "User")[:32].replace("<", "").replace(">", "")
    return f'{emoji} Delivered — <a href="tg://user?id={user.id}">{safe_name}</a>'


def format_audio_info(title: str = "", artist: str = "", duration: str = "") -> str:
    """Legacy compat — returns basic audio info string"""
    parts = []
    if title:
        parts.append(f"<b>{title[:64]}</b>")
    if artist:
        parts.append(artist[:64])
    if duration:
        parts.append(duration)
    return " — ".join(parts) if parts else ""


async def format_welcome_legacy(user: User, user_id: int) -> str:
    return await format_welcome(user, user_id)


async def format_help_video_legacy() -> str:
    return await format_help_video()


def format_help_music_legacy() -> str:
    return format_help_music()
