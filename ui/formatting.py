"""
NAGU DOWNLOADER — UI Formatting System
Clean • Premium • Telegram Native

Design principles:
  - Global header on ALL messages: ◇─◇ 𝐃ᴏᴡɴʟᴏᴀᴅᴇʀ 𝐁ᴏᴛ ◇─◇
  - All emojis from DB via get_emoji_async() — NEVER hardcoded
  - Small-caps Unicode font for all headings
  - Clickable user mentions via HTML
  - All parse_mode = HTML
  - No sticker requests, no debug info, no stack traces

Emoji keys (all uppercase in DB):
  YT, INSTA, PINTEREST, MUSIC, VIDEO, SPOTIFY, PLAYLIST
  SUCCESS, ERROR, PROCESS, FAST, DOWNLOAD, COMPLETE, LOADING, CHECK, DELIVERED
  BROADCAST, INFO, ID, USER, PING, PIN
  STAR, FIRE, ROCKET, CROWN, DIAMOND, ZAP, WAVE
"""
from __future__ import annotations
from typing import List
from aiogram.types import User

from ui.emoji_config import get_emoji, get_emoji_async


# ─── Global header ────────────────────────────────────────────────────────────

HEADER = "◇─◇ 𝐃ᴏᴡɴʟᴏᴀᴅᴇʀ 𝐁ᴏᴛ ◇─◇"


def _h(body: str) -> str:
    """Prepend global header to any message body."""
    return f"{HEADER}\n\n{body}"


# ─── Core primitives ──────────────────────────────────────────────────────────

def ui_title(text: str) -> str:
    """Return text as-is (Unicode bold/small-caps already applied by callers)."""
    return text


def mention(user: User) -> str:
    """Clickable HTML user mention"""
    if not user:
        return "Unknown"
    name = (user.first_name or "User")[:32]
    safe = name.replace("<", "").replace(">", "")
    return f'<a href="tg://user?id={user.id}">{safe}</a>'


async def format_delivered_with_mention(user_id: int, first_name: str) -> str:
    """
    Returns a clean delivered caption with clickable user mention.
    Output: ✓ Delivered — <Name>
    """
    emoji = await get_emoji_async("DELIVERED")
    safe_name = (first_name or "User")[:32].replace("<", "").replace(">", "")
    return f'{emoji} Delivered — <a href="tg://user?id={user_id}">{safe_name}</a>'


def format_delivered_with_mention_sync(user_id: int, first_name: str) -> str:
    """Sync fallback for format_delivered_with_mention."""
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


def code_panel(lines: List[str], width: int = 32) -> str:
    """Monospace panel wrapped in <code> block"""
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


# ─── Processing indicators ────────────────────────────────────────────────────

async def format_downloading() -> str:
    """Processing/downloading indicator"""
    proc = await get_emoji_async("PROCESS")
    dl   = await get_emoji_async("DOWNLOAD")
    return _h(f"{proc} 𝐏ʀᴏᴄᴇꜱꜱɪɴɢ...\n{dl} 𝐅ᴇᴛᴄʜɪɴɢ 𝐅ɪʟᴇ")


async def format_processing(platform: str = "") -> str:
    """Initial processing message"""
    proc  = await get_emoji_async("PROCESS")
    fast  = await get_emoji_async("FAST")
    music = await get_emoji_async("MUSIC")
    pin   = await get_emoji_async("PIN")
    dl    = await get_emoji_async("DOWNLOAD")

    if platform == "youtube":
        return _h(f"{proc} 𝐏ʀᴏᴄᴇꜱꜱɪɴɢ...\n{dl} 𝐅ᴇᴛᴄʜɪɴɢ 𝐅ɪʟᴇ")
    elif platform == "shorts":
        return _h(f"{fast} 𝐏ʀᴏᴄᴇꜱꜱɪɴɢ 𝐒ʜᴏʀᴛ...\n{dl} 𝐅ᴇᴛᴄʜɪɴɢ 𝐅ɪʟᴇ")
    elif platform == "ytmusic":
        return _h(f"{music} 𝐏ʀᴏᴄᴇꜱꜱɪɴɢ 𝐀ᴜᴅɪᴏ...\n{dl} 𝐅ᴇᴛᴄʜɪɴɢ 𝐅ɪʟᴇ")
    elif platform == "instagram":
        return _h(f"{fast} 𝐅ᴇᴛᴄʜɪɴɢ 𝐌ᴇᴅɪᴀ...\n{dl} 𝐅ᴇᴛᴄʜɪɴɢ 𝐅ɪʟᴇ")
    elif platform == "pinterest":
        return _h(f"{pin} 𝐅ᴇᴛᴄʜɪɴɢ 𝐌ᴇᴅɪᴀ...\n{dl} 𝐅ᴇᴛᴄʜɪɴɢ 𝐅ɪʟᴇ")
    elif platform == "spotify":
        return _h(f"{music} 𝐏ʀᴏᴄᴇꜱꜱɪɴɢ 𝐓ʀᴀᴄᴋ...\n{dl} 𝐅ᴇᴛᴄʜɪɴɢ 𝐅ɪʟᴇ")
    return _h(f"{proc} 𝐏ʀᴏᴄᴇꜱꜱɪɴɢ...\n{dl} 𝐅ᴇᴛᴄʜɪɴɢ 𝐅ɪʟᴇ")


async def format_progress(pct: int, label: str = "𝐅ᴇᴛᴄʜɪɴɢ 𝐅ɪʟᴇ") -> str:
    """Download progress bar"""
    dl = await get_emoji_async("DOWNLOAD")
    width = 10
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return _h(f"{dl} 𝐃ᴏᴡɴʟᴏᴀᴅɪɴɢ\n\n[{bar}] {pct}%\n{label}")


async def format_delivered() -> str:
    """Plain delivery confirmation"""
    emoji = await get_emoji_async("SUCCESS")
    check = await get_emoji_async("CHECK")
    return _h(f"{emoji} 𝐃ᴏɴᴇ\n{check} 𝐒ᴇɴᴛ 𝐒ᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ")


async def format_error(message: str | None = None) -> str:
    """Global error message — never show debug info"""
    emoji = await get_emoji_async("ERROR")
    return _h(f"{emoji} 𝐅ᴀɪʟᴇᴅ\n𝐔ɴᴀʙʟᴇ ᴛᴏ ᴘʀᴏᴄᴇꜱꜱ ʟɪɴᴋ.")


# ─── /start ───────────────────────────────────────────────────────────────────

async def format_welcome(user: User, user_id: int) -> str:
    """Welcome message"""
    wave = await get_emoji_async("WAVE")
    yt   = await get_emoji_async("YT")
    ig   = await get_emoji_async("INSTA")
    sp   = await get_emoji_async("SPOTIFY")
    pin  = await get_emoji_async("PINTEREST")
    return _h(
        f"{wave} 𝐖ᴇʟᴄᴏᴍᴇ\n\n"
        "ꜱᴇɴᴅ ᴀ ʟɪɴᴋ ꜰʀᴏᴍ:\n\n"
        f"{yt} 𝐘ᴏᴜ𝐓ᴜʙᴇ\n"
        f"{ig} 𝐈ɴꜱᴛᴀɢʀᴀᴍ\n"
        f"{sp} 𝐒ᴘᴏᴛɪꜰʏ\n"
        f"{pin} 𝐏ɪɴᴛᴇʀᴇꜱᴛ\n\n"
        "𝐉ᴜꜱᴛ ᴘᴀꜱᴛᴇ ᴛʜᴇ ʟɪɴᴋ."
    )


# ─── /help ────────────────────────────────────────────────────────────────────

async def format_help() -> str:
    """Single unified help message"""
    info   = await get_emoji_async("INFO")
    rocket = await get_emoji_async("ROCKET")
    yt     = await get_emoji_async("YT")
    sp     = await get_emoji_async("SPOTIFY")
    ig     = await get_emoji_async("INSTA")
    pin    = await get_emoji_async("PINTEREST")
    return _h(
        f"{info} 𝐂ᴏᴍᴍᴀɴᴅꜱ\n\n"
        "/start — 𝐒ᴛᴀʀᴛ\n"
        "/help — 𝐋ɪꜱᴛ\n"
        "/id — 𝐘ᴏᴜʀ 𝐈ᴅ\n"
        "/chatid — 𝐂ʜᴀᴛ 𝐈ᴅ\n"
        "/myinfo — 𝐀ᴄᴄᴏᴜɴᴛ\n"
        "/mp3 — 𝐄xᴛʀᴀᴄᴛ 𝐀ᴜᴅɪᴏ\n"
        "/broadcast — 𝐀ᴅᴍɪɴ 𝐎ɴʟʏ\n\n"
        f"{rocket} 𝐒ᴜᴘᴘᴏʀᴛ\n\n"
        f"{yt} 𝐘ᴏᴜ𝐓ᴜʙᴇ\n"
        f"{sp} 𝐒ᴘᴏᴛɪꜰʏ\n"
        f"{ig} 𝐈ɴꜱᴛᴀɢʀᴀᴍ\n"
        f"{pin} 𝐏ɪɴᴛᴇʀᴇꜱᴛ"
    )


# Legacy compat
async def format_help_video() -> str:
    return await format_help()


def format_help_music() -> str:
    return ""


def format_help_info() -> str:
    return ""


# ─── /myinfo ──────────────────────────────────────────────────────────────────

async def format_myinfo(user: User, chat_title: str = None) -> str:
    """Account info"""
    user_emoji = await get_emoji_async("USER")
    username = f"@{user.username}" if user.username else "—"
    chat_type = "private" if not chat_title else "group"
    safe_name = (user.first_name or "—")[:32].replace("<", "").replace(">", "")
    user_link = f'<a href="tg://user?id={user.id}">{safe_name}</a>'
    return _h(
        f"{user_emoji} 𝐀ᴄᴄᴏᴜɴᴛ 𝐈ɴꜰᴏ\n\n"
        f"𝐍ᴀᴍᴇ: {user_link}\n"
        f"𝐋ᴀꜱᴛ 𝐍ᴀᴍᴇ: {(user.last_name or '—')[:32]}\n"
        f"𝐔ꜱᴇʀɴᴀᴍᴇ: {username}\n"
        f"𝐈ᴅ: <code>{user.id}</code>\n"
        f"𝐋ᴀɴɢᴜᴀɢᴇ: {user.language_code or '—'}\n"
        f"𝐂ʜᴀᴛ 𝐓ʏᴘᴇ: {chat_type}"
    )


# ─── /id ──────────────────────────────────────────────────────────────────────

async def format_id(user: User, label: str = "YOUR  ID") -> str:
    """User ID info"""
    id_emoji = await get_emoji_async("ID")
    username = f"@{user.username}" if user.username else "—"
    is_other = "USER" in label.upper()
    title = "𝐔ꜱᴇʀ 𝐈ᴅ" if is_other else "𝐘ᴏᴜʀ 𝐈ᴅ"
    safe_name = (user.first_name or "—")[:32].replace("<", "").replace(">", "")
    user_link = f'<a href="tg://user?id={user.id}">{safe_name}</a>'
    return _h(
        f"{id_emoji} {title}\n\n"
        f"𝐍ᴀᴍᴇ: {user_link}\n"
        f"𝐔ꜱᴇʀɴᴀᴍᴇ: {username}\n"
        f"𝐈ᴅ: <code>{user.id}</code>"
    )


# ─── /chatid ──────────────────────────────────────────────────────────────────

async def format_chatid(chat_id: int, chat_title: str, chat_type: str) -> str:
    """Chat ID info"""
    info = await get_emoji_async("INFO")
    return _h(
        f"{info} 𝐂ʜᴀᴛ 𝐈ᴅ\n\n"
        f"𝐂ʜᴀᴛ: {chat_title[:32]}\n"
        f"𝐓ʏᴘᴇ: {chat_type}\n"
        f"𝐈ᴅ: <code>{chat_id}</code>"
    )


# ─── Admin panel ──────────────────────────────────────────────────────────────

async def format_admin_panel(stats: dict = None) -> str:
    """Admin panel"""
    broadcast = await get_emoji_async("BROADCAST")
    text = (
        f"{broadcast} 𝐀ᴅᴍɪɴ 𝐏ᴀɴᴇʟ\n\n"
        "/broadcast — 𝐒ᴇɴᴅ ᴛᴏ ᴀʟʟ\n"
        "/assign — 𝐂ᴏɴꜰɪɢᴜʀᴇ ᴇᴍᴏᴊɪ\n"
        "/stats — 𝐔ꜱᴇʀ ꜱᴛᴀᴛꜱ\n"
    )
    if stats:
        text += (
            f"\n𝐔ꜱᴇʀꜱ: {stats.get('users', 0)}\n"
            f"𝐆ʀᴏᴜᴘꜱ: {stats.get('groups', 0)}"
        )
    return _h(text)


# ─── /status ──────────────────────────────────────────────────────────────────

async def format_status(active_jobs: int = 0, queue: int = 0, uptime: str = "—") -> str:
    diamond = await get_emoji_async("DIAMOND")
    return _h(
        f"{diamond} 𝐒ᴛᴀᴛᴜꜱ\n\n"
        f"𝐀ᴄᴛɪᴠᴇ: {active_jobs}\n"
        f"𝐐ᴜᴇᴜᴇ: {queue}\n"
        f"𝐔ᴘᴛɪᴍᴇ: {uptime}"
    )


# ─── Spotify progress ─────────────────────────────────────────────────────────

async def format_playlist_detected() -> str:
    sp    = await get_emoji_async("SPOTIFY")
    music = await get_emoji_async("MUSIC")
    return _h(f"{sp} 𝐏ʟᴀʏʟɪꜱᴛ 𝐃ᴇᴛᴇᴄᴛᴇᴅ\n\n{music} 𝐒ᴛᴀʀᴛɪɴɢ ᴅᴏᴡɴʟᴏᴀᴅ...")


def format_playlist_progress(name: str, done: int, total: int) -> str:
    """Spotify playlist progress bar"""
    if total > 0:
        pct = min(100, int(done * 100 / total))
    else:
        pct = 0
    width = 10
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    name_short = (name or "Playlist")[:30]
    return (
        f"{HEADER}\n\n"
        f"🎧 𝐏ʟᴀʏʟɪꜱᴛ: {name_short}\n\n"
        f"[{bar}] {pct}%\n"
        f"{done} / {total}"
    )


async def format_playlist_final(user: User, name: str, total: int, sent: int, failed: int) -> str:
    """Spotify playlist completion"""
    crown   = await get_emoji_async("CROWN")
    success = await get_emoji_async("SUCCESS")
    safe_name = (user.first_name or "User")[:32].replace("<", "").replace(">", "")
    user_link = f'<a href="tg://user?id={user.id}">{safe_name}</a>'
    name_short = (name or "Playlist")[:30]
    return _h(
        f"{crown} 𝐏ʟᴀʏʟɪꜱᴛ 𝐅ɪɴɪꜱʜᴇᴅ\n\n"
        f"𝐍ᴀᴍᴇ: {name_short}\n"
        f"𝐓ᴏᴛᴀʟ: {total}\n"
        f"𝐒ᴇɴᴛ: {sent}\n"
        f"𝐅ᴀɪʟᴇᴅ: {failed}\n\n"
        f"{success} 𝐀ʟʟ 𝐅ɪʟᴇꜱ 𝐒ᴇɴᴛ\n\n"
        f"{user_link}"
    )


def format_playlist_dm_complete(name: str) -> str:
    """Final DM message after playlist delivery"""
    return f"{HEADER}\n\n🎧 𝐏ʟᴀʏʟɪꜱᴛ 𝐃𝐞𝐥𝐢𝐯𝐞𝐫𝐞𝐝."


async def format_spotify_complete(user: User, total: int, sent: int) -> str:
    """Legacy compat"""
    return await format_playlist_final(user, "", total, sent, total - sent)


# ─── YouTube playlist ─────────────────────────────────────────────────────────

def format_yt_playlist_mode(playlist_name: str) -> str:
    """Mode selection for YouTube playlist"""
    name_short = (playlist_name or "Playlist")[:40]
    return f"{HEADER}\n\n🎬 𝐏ʟᴀʏʟɪꜱᴛ: {name_short}\n\n𝐂ʜᴏᴏꜱᴇ 𝐃ᴏᴡɴʟᴏᴀᴅ 𝐌ᴏᴅᴇ:"


def format_yt_audio_quality() -> str:
    """Audio quality selection"""
    return f"{HEADER}\n\n🎵 𝐀ᴜᴅɪᴏ 𝐐ᴜᴀʟɪᴛʏ\n\n𝐂ʜᴏᴏꜱᴇ ʏᴏᴜʀ ᴘʀᴇꜰᴇʀʀᴇᴅ ᴀᴜᴅɪᴏ ǫᴜᴀʟɪᴛʏ:"


def format_yt_video_quality() -> str:
    """Video quality selection"""
    return f"{HEADER}\n\n🎥 𝐕ɪᴅᴇᴏ 𝐐ᴜᴀʟɪᴛʏ\n\n𝐂ʜᴏᴏꜱᴇ ʏᴏᴜʀ ᴘʀᴇꜰᴇʀʀᴇᴅ ᴠɪᴅᴇᴏ ǫᴜᴀʟɪᴛʏ:"


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
        f"{HEADER}\n\n"
        f"🎬 𝐏ʟᴀʏʟɪꜱᴛ: {name_short}\n\n"
        f"[{bar}] {pct}%\n"
        f"{done} / {total}"
    )


async def format_yt_playlist_final(name: str, total: int, sent: int, failed: int) -> str:
    """YouTube playlist completion message"""
    crown   = await get_emoji_async("CROWN")
    success = await get_emoji_async("SUCCESS")
    name_short = (name or "Playlist")[:30]
    return _h(
        f"{crown} 𝐏ʟᴀʏʟɪꜱᴛ 𝐅ɪɴɪꜱʜᴇᴅ\n\n"
        f"𝐍ᴀᴍᴇ: {name_short}\n"
        f"𝐓ᴏᴛᴀʟ: {total}\n"
        f"𝐒ᴇɴᴛ: {sent}\n"
        f"𝐅ᴀɪʟᴇᴅ: {failed}\n\n"
        f"{success} 𝐀ʟʟ 𝐅ɪʟᴇꜱ 𝐒ᴇɴᴛ"
    )


# ─── Broadcast ────────────────────────────────────────────────────────────────

async def format_broadcast_started() -> str:
    bc = await get_emoji_async("BROADCAST")
    return _h(f"{bc} 𝐁ʀᴏᴀᴅᴄᴀꜱᴛ 𝐒ᴛᴀʀᴛᴇᴅ")


async def format_broadcast_report(total_users: int, total_groups: int, success: int, failed: int) -> str:
    bc = await get_emoji_async("BROADCAST")
    return _h(
        f"{bc} 𝐁ʀᴏᴀᴅᴄᴀꜱᴛ 𝐑ᴇᴘᴏʀᴛ\n\n"
        f"𝐔ꜱᴇʀꜱ: {total_users:,}\n"
        f"𝐆ʀᴏᴜᴘꜱ: {total_groups:,}\n"
        f"𝐒ᴜᴄᴄᴇꜱꜱ: {success:,}\n"
        f"𝐅ᴀɪʟᴇᴅ: {failed:,}"
    )


# ─── Emoji assign system ──────────────────────────────────────────────────────

EMOJI_POSITIONS = {
    "YOUTUBE":    "🎬 YouTube",
    "INSTAGRAM":  "📸 Instagram",
    "PINTEREST":  "📌 Pinterest",
    "MUSIC":      "🎵 Music",
    "VIDEO":      "🎥 Video",
    "SPOTIFY":    "🎧 Spotify",
    "PLAYLIST":   "🎶 Playlist",
    "DELIVERED":  "✓ Delivered",
    "SUCCESS":    "✅ Success",
    "ERROR":      "⚠ Error",
    "PROCESS":    "⏳ Processing",
    "FAST":       "⚡ Fast",
    "DOWNLOAD":   "📥 Download",
    "COMPLETE":   "🎉 Complete",
    "LOADING":    "⏳ Loading",
    "CHECK":      "✅ Check",
    "BROADCAST":  "📢 Broadcast",
    "INFO":       "ℹ Info",
    "ID":         "🆔 ID",
    "USER":       "👤 User",
    "PING":       "🏓 Ping",
    "PIN":        "📌 Pin",
    "STAR":       "⭐ Star",
    "FIRE":       "🔥 Fire",
    "ROCKET":     "🚀 Rocket",
    "CROWN":      "👑 Crown",
    "DIAMOND":    "💎 Diamond",
    "ZAP":        "⚡ Zap",
    "WAVE":       "👋 Wave",
}


def format_assign_menu(configured_keys: set) -> str:
    lines = [f"{HEADER}\n\n𝐄ᴍᴏᴊɪ 𝐒ᴇᴛᴜᴘ\n"]
    for key, label in EMOJI_POSITIONS.items():
        status = "[Configured]" if key in configured_keys else "[Not set]"
        lines.append(f"{label}  →  {status}")
    return "\n".join(lines)


def format_assign_prompt(label: str) -> str:
    return (
        f"{HEADER}\n\n"
        f"𝐒ᴇᴛ 𝐄ᴍᴏᴊɪ\n\n"
        f"Send a premium emoji or standard emoji for:\n"
        f"<b>{label}</b>\n\n"
        f"<i>Tip: Send a Telegram premium custom emoji, or type a regular emoji like 🎵</i>"
    )


def format_assign_updated() -> str:
    return f"{HEADER}\n\n𝐄ᴍᴏᴊɪ 𝐔ᴘᴅᴀᴛᴇᴅ ✓"


# ─── Stats ────────────────────────────────────────────────────────────────────

async def format_stats(users: int, groups: int) -> str:
    info = await get_emoji_async("INFO")
    return _h(
        f"{info} 𝐁ᴏᴛ 𝐒ᴛᴀᴛꜱ\n\n"
        f"𝐔ꜱᴇʀꜱ: {users}\n"
        f"𝐆ʀᴏᴜᴘꜱ: {groups}"
    )


# ─── Legacy compat ────────────────────────────────────────────────────────────

async def format_user_info(user: User) -> str:
    """Legacy compat — returns user info panel"""
    return await format_myinfo(user)


async def format_download_complete(user: User) -> str:
    """Legacy compat — returns delivered confirmation with mention"""
    emoji = await get_emoji_async("SUCCESS")
    safe_name = (user.first_name or "User")[:32].replace("<", "").replace(">", "")
    return f'{emoji} Delivered — <a href="tg://user?id={user.id}">{safe_name}</a>'


def format_audio_info(title: str = "", artist: str = "", duration: str = "") -> str:
    """Legacy compat — returns basic audio info string"""
    parts = []
    if title:
        parts.append(title[:64])
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
