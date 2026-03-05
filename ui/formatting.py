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
import html
import re
import unicodedata
from typing import List, Optional
from aiogram.types import User, InlineKeyboardMarkup, InlineKeyboardButton

from ui.emoji_config import get_emoji, get_emoji_async

# ─── Telegram limits ──────────────────────────────────────────────────────────

TG_CAPTION_LIMIT = 1024   # Telegram hard cap for captions
TG_MESSAGE_LIMIT = 4096   # Telegram hard cap for messages


def _escape(text: str) -> str:
    """
    Properly HTML-escape a plain-text string for use inside Telegram HTML captions.
    Escapes &, <, >, " so they cannot break the HTML parser.
    """
    return html.escape(str(text), quote=True)


def safe_caption(text: str, limit: int = TG_CAPTION_LIMIT) -> str:
    """
    Centralized caption sanitizer — MUST be called on every caption before
    sending to Telegram to prevent ENTITY_TEXT_INVALID errors.

    Rules:
    - Converts to str (handles None / bytes)
    - Strips mixed markdown characters that break HTML parse_mode
    - Removes control characters (except newline/tab)
    - Trims to `limit` characters (default 1024 — Telegram caption hard cap)
    - Removes dangling open HTML tags at the truncation boundary
    - Returns empty string only if input is empty/None

    IMPORTANT: This function does NOT re-escape already-escaped HTML.
    Callers must ensure user-provided text is escaped via _escape() before
    embedding in HTML templates.
    """
    if not text:
        return ""
    text = str(text)

    # Strip mixed markdown characters that conflict with HTML parse_mode
    # These cause ENTITY_TEXT_INVALID when Telegram tries to parse HTML
    # but finds markdown-style formatting mixed in.
    text = re.sub(r"(?<!\w)[*_`~]{1,3}(?!\w)", "", text)

    # Remove control characters (except \n \t \r which are valid in captions)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Trim to limit — avoid cutting in the middle of an HTML tag
    if len(text) > limit:
        trimmed = text[:limit]
        # Remove any dangling open tag at the truncation boundary
        trimmed = re.sub(r"<[^>]*$", "", trimmed)
        return trimmed

    return text


def build_safe_media_caption(user_id: int, first_name: str, delivered_emoji: str = "✓") -> str:
    """
    Build a sanitized media caption with requester attribution.

    Format:
        ✓ Delivered  ·  "<Name>"

    Name is in quotes, clickable.
    """
    try:
        safe_name = _escape((first_name or "User")[:32])
        raw = f'{delivered_emoji} Delivered  ·  "<a href="tg://user?id={user_id}">{safe_name}</a>"'
        return safe_caption(raw)
    except Exception:
        return "✓ Delivered"


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
    """Clickable HTML user mention — properly HTML-escaped."""
    if not user:
        return "Unknown"
    name = (user.first_name or "User")[:32]
    safe = _escape(name)
    return f'<a href="tg://user?id={user.id}">{safe}</a>'


async def format_delivered_with_mention(user_id: int, first_name: str) -> str:
    """Delivered caption:  ✓ Delivered  ·  "Name" (clickable, quoted)"""
    emoji = await get_emoji_async("DELIVERED")
    safe_name = _escape((first_name or "User")[:32])
    raw = f'{emoji} Delivered  ·  "<a href="tg://user?id={user_id}">{safe_name}</a>"'
    return safe_caption(raw)


def format_delivered_with_mention_sync(user_id: int, first_name: str) -> str:
    """Sync fallback — Delivered  ·  "Name" (clickable, quoted)"""
    emoji = get_emoji("DELIVERED")
    safe_name = _escape((first_name or "User")[:32])
    raw = f'{emoji} Delivered  ·  "<a href="tg://user?id={user_id}">{safe_name}</a>"'
    return safe_caption(raw)


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
    """Legacy compat stub — returns content without ugly blockquote wrapper"""
    return content


def styled_text(text: str) -> str:
    """Legacy compat — returns text as-is"""
    return text


def premium_panel(title: str, lines: list) -> str:
    """Legacy compat stub — returns clean emoji-driven text, no borders"""
    return f"{title}\n\n" + "\n".join(lines)


def code_panel(lines: List[str], width: int = 32) -> str:
    """Legacy compat stub — returns clean text, no ugly box-drawing borders"""
    return "\n".join(lines)


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
    """
    Branded welcome message for /start.

    Structure:
      Header → Tagline → Platforms → Instruction

    All platform emojis fetched dynamically from emoji config (Redis → PREMIUM → DEFAULT).
    No hardcoded emojis. No hardcoded links.
    """
    yt   = await get_emoji_async("YT")
    ig   = await get_emoji_async("INSTA")
    sp   = await get_emoji_async("SPOTIFY")
    pin  = await get_emoji_async("PINTEREST")
    zap  = await get_emoji_async("ZAP")

    wave = await get_emoji_async("WAVE")
    return (
        f"{wave} <b>Welcome to Nagu Downloader</b>\n\n"
        f"{zap} Fast &amp; powerful media downloader\n\n"
        f"  {yt}  YouTube\n"
        f"  {ig}  Instagram\n"
        f"  {sp}  Spotify\n"
        f"  {pin}  Pinterest\n\n"
        "Just paste a link and I'll handle the rest ✨"
    )


async def build_start_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    """
    Centralized /start inline keyboard builder.

    Layout:
      Row 1: 📥 Download  |  📊 Status
      Row 2: 📜 Help      |  ⚙ Settings
      Row 3: 📢 Updates   |  💬 Support   (hidden if not configured)
      Row 4: 👑 Owner                     (hidden if OWNER_ID not set)
      Row 5: ➕ Add Me To Group           (URL button — appears BLUE)

    Rules:
    - URL buttons appear blue in Telegram.
    - Callback buttons appear gray.
    - ➕ Add Me To Group MUST be a URL button.
    - Support/Updates hidden if not configured.
    - Owner uses tg://user?id=OWNER_ID (no hardcoded username).
    - bot_username must be passed dynamically — never hardcoded.
    """
    from core.config import config

    rows = []

    # Row 1: Download | Status (colored)
    rows.append([
        InlineKeyboardButton(text="📥 Download", callback_data="cb_download", style="primary"),
        InlineKeyboardButton(text="📊 Status",   callback_data="status", style="success"),
    ])

    # Row 2: Help | Settings
    rows.append([
        InlineKeyboardButton(text="📜 Help",     callback_data="cb_help"),
        InlineKeyboardButton(text="⚙ Settings",  callback_data="cb_settings"),
    ])

    # Row 3: Manage Group
    rows.append([
        InlineKeyboardButton(text="👮 Manage Group", callback_data="cb_manage"),
    ])

    # Row 4: Updates | Support (only if configured)
    row3 = []
    if config.UPDATE_CHANNEL:
        row3.append(InlineKeyboardButton(text="📢 Updates", url=config.UPDATE_CHANNEL))
    if config.GROUP_LINK:
        row3.append(InlineKeyboardButton(text="💬 Support", url=config.GROUP_LINK))
    if row3:
        rows.append(row3)

    # Row 4: Owner (only if OWNER_ID configured)
    if config.OWNER_ID:
        rows.append([
            InlineKeyboardButton(
                text="👑 Owner",
                url=f"tg://user?id={config.OWNER_ID}",
            )
        ])

    # Row 5: Add Me To Group — URL button (appears BLUE in Telegram)
    rows.append([
        InlineKeyboardButton(
            text="➕ Add Me To Group",
            url=f"https://t.me/{bot_username}?startgroup=true",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_back_keyboard() -> InlineKeyboardMarkup:
    """Single '← Back' button to return to main menu."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="← Back", callback_data="cb_back"),
    ]])


def build_manage_keyboard() -> InlineKeyboardMarkup:
    """Group management submenu — 6 categories."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🛡 Moderation", callback_data="mg_mod"),
            InlineKeyboardButton(text="📌 Pins", callback_data="mg_pins"),
        ],
        [
            InlineKeyboardButton(text="⚠ Warnings", callback_data="mg_warn"),
            InlineKeyboardButton(text="🧹 Cleanup", callback_data="mg_clean"),
        ],
        [
            InlineKeyboardButton(text="📊 Group Info", callback_data="mg_info"),
            InlineKeyboardButton(text="👥 Members", callback_data="mg_members"),
        ],
        [InlineKeyboardButton(text="← Back", callback_data="cb_back")],
    ])


def build_manage_back_keyboard() -> InlineKeyboardMarkup:
    """Back to Manage Group menu."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="← Back to Manage", callback_data="cb_manage"),
    ]])


# ─── /help ────────────────────────────────────────────────────────────────────

async def format_help() -> str:
    """Help message — clean, organized"""
    info   = await get_emoji_async("INFO")
    rocket = await get_emoji_async("ROCKET")
    yt     = await get_emoji_async("YT")
    sp     = await get_emoji_async("SPOTIFY")
    ig     = await get_emoji_async("INSTA")
    pin    = await get_emoji_async("PINTEREST")
    return _h(
        f"{info} <b>Commands</b>\n\n"
        "/start  ·  Start the bot\n"
        "/help  ·  Show this help\n"
        "/id  ·  Get user ID\n"
        "/chatid  ·  Get chat ID\n"
        "/myinfo  ·  Account details\n"
        "/mp3  ·  Extract audio\n"
        "/ping  ·  Check latency\n"
        "/status  ·  Bot status\n\n"
        f"{rocket} <b>Supported Platforms</b>\n\n"
        f"  {yt}  YouTube  ·  Videos, Shorts, Music\n"
        f"  {sp}  Spotify  ·  Tracks &amp; Playlists\n"
        f"  {ig}  Instagram  ·  Reels &amp; Posts\n"
        f"  {pin}  Pinterest  ·  Videos &amp; Photos\n\n"
        "👮 <b>Group Admin</b>\n\n"
        "/ban · /kick · /mute · /unmute\n"
        "/pin · /unpin · /purge"
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
    """Account info — clean layout"""
    user_emoji = await get_emoji_async("USER")
    username = f"@{_escape(user.username)}" if user.username else "not set"
    safe_name = _escape((user.first_name or "User")[:32])
    user_link = f'<a href="tg://user?id={user.id}">{safe_name}</a>'
    last = _escape((user.last_name or "")[:32])
    lang = _escape(user.language_code or "en")
    return _h(
        f"{user_emoji} <b>Account Info</b>\n\n"
        f"Name  ·  {user_link}\n"
        f"Last  ·  {last or 'not set'}\n"
        f"Username  ·  {username}\n"
        f"ID  ·  <code>{user.id}</code>\n"
        f"Language  ·  {lang}"
    )


# ─── /id ──────────────────────────────────────────────────────────────────────

async def format_id(user: User, label: str = "YOUR  ID") -> str:
    """User ID info — clean"""
    id_emoji = await get_emoji_async("ID")
    username = f"@{_escape(user.username)}" if user.username else "not set"
    is_other = "USER" in label.upper()
    title = "User ID" if is_other else "Your ID"
    safe_name = _escape((user.first_name or "User")[:32])
    user_link = f'<a href="tg://user?id={user.id}">{safe_name}</a>'
    return _h(
        f"{id_emoji} <b>{title}</b>\n\n"
        f"Name  ·  {user_link}\n"
        f"Username  ·  {username}\n"
        f"ID  ·  <code>{user.id}</code>"
    )


# ─── /chatid ──────────────────────────────────────────────────────────────────

async def format_chatid(chat_id: int, chat_title: str, chat_type: str) -> str:
    """Chat ID info — clean"""
    info = await get_emoji_async("INFO")
    safe_title = _escape(chat_title[:32])
    return _h(
        f"{info} <b>Chat ID</b>\n\n"
        f"Chat  ·  {safe_title}\n"
        f"Type  ·  {chat_type}\n"
        f"ID  ·  <code>{chat_id}</code>"
    )


# ─── Admin panel ──────────────────────────────────────────────────────────────

async def format_admin_panel(stats: dict = None) -> str:
    """Admin panel — clean"""
    crown = await get_emoji_async("CROWN")
    text = (
        f"{crown} <b>Admin Panel</b>\n\n"
        "/broadcast  ·  Send to all users\n"
        "/assign  ·  Configure emojis\n"
        "/stats  ·  User statistics\n"
        "/addpxy  ·  Add proxies\n"
        "/rm  ·  Remove proxy\n"
        "/clean  ·  Scan proxies\n"
    )
    if stats:
        text += (
            f"\nUsers  ·  {stats.get('users', 0)}\n"
            f"Groups  ·  {stats.get('groups', 0)}"
        )
    return _h(text)


# ─── /status ──────────────────────────────────────────────────────────────────

async def format_status(active_jobs: int = 0, queue: int = 0, uptime: str = "—") -> str:
    diamond = await get_emoji_async("DIAMOND")
    rocket = await get_emoji_async("ROCKET")
    return _h(
        f"{diamond} <b>Bot Status</b>\n\n"
        f"{rocket} Active  ·  {active_jobs}\n"
        f"Queue  ·  {queue}\n"
        f"Uptime  ·  {uptime}"
    )


# ─── Spotify progress ─────────────────────────────────────────────────────────

async def format_playlist_detected() -> str:
    sp    = await get_emoji_async("SPOTIFY")
    music = await get_emoji_async("MUSIC")
    return _h(f"{sp} <b>Playlist Detected</b>\n\n{music} Starting download...")


def format_playlist_progress(name: str, done: int, total: int) -> str:
    """Spotify playlist progress bar"""
    if total > 0:
        pct = min(100, int(done * 100 / total))
    else:
        pct = 0
    width = 10
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    name_short = _escape((name or "Playlist")[:30])
    return (
        f"{HEADER}\n\n"
        f"🎧 𝐏ʟᴀʏʟɪꜱᴛ: {name_short}\n\n"
        f"[{bar}] {pct}%\n"
        f"{done} / {total}"
    )


async def format_playlist_final(user: User, name: str, total: int, sent: int, failed: int) -> str:
    """Spotify playlist completion — clean"""
    complete = await get_emoji_async("COMPLETE")
    success  = await get_emoji_async("SUCCESS")
    safe_name = _escape((user.first_name or "User")[:32])
    user_link = f'"<a href="tg://user?id={user.id}">{safe_name}</a>"'
    name_short = _escape((name or "Playlist")[:30])
    return _h(
        f"{complete} <b>Playlist Complete</b>\n\n"
        f"Name  ·  {name_short}\n"
        f"Total  ·  {total}\n"
        f"Sent  ·  {sent}\n"
        f"Failed  ·  {failed}\n\n"
        f"{success} All files sent to {user_link}"
    )


def format_playlist_dm_complete(name: str) -> str:
    """Final DM message after playlist delivery"""
    return f"{HEADER}\n\n🎧 <b>Playlist Delivered</b>  ·  Enjoy your music!"


async def format_spotify_complete(user: User, total: int, sent: int) -> str:
    """Legacy compat"""
    return await format_playlist_final(user, "", total, sent, total - sent)


# ─── YouTube playlist (REMOVED — stubs for import compat) ─────────────────────

def format_yt_playlist_mode(playlist_name: str) -> str:
    """DEPRECATED: YT playlist feature removed"""
    return ""

def format_yt_audio_quality() -> str:
    """DEPRECATED: YT playlist feature removed"""
    return ""

def format_yt_video_quality() -> str:
    """DEPRECATED: YT playlist feature removed"""
    return ""

def format_yt_playlist_progress(name: str, done: int, total: int) -> str:
    """DEPRECATED: YT playlist feature removed"""
    return ""

async def format_yt_playlist_final(name: str, total: int, sent: int, failed: int) -> str:
    """DEPRECATED: YT playlist feature removed"""
    return ""


# ─── Broadcast ────────────────────────────────────────────────────────────────

async def format_broadcast_started() -> str:
    bc = await get_emoji_async("BROADCAST")
    return _h(f"{bc} <b>Broadcast Started</b>\n\nSending to all users and groups...")


async def format_broadcast_report(total_users: int, total_groups: int, success: int, failed: int) -> str:
    bc = await get_emoji_async("BROADCAST")
    check = await get_emoji_async("CHECK")
    return _h(
        f"{bc} <b>Broadcast Report</b>\n\n"
        f"Users  ·  {total_users:,}\n"
        f"Groups  ·  {total_groups:,}\n"
        f"{check} Sent  ·  {success:,}\n"
        f"Failed  ·  {failed:,}"
    )


# ─── Emoji assign system ──────────────────────────────────────────────────────

# Keys MUST match what get_emoji_async() uses and what Redis stores as "emoji:{KEY}"
EMOJI_POSITIONS = {
    "YT":         "🎬 YouTube",
    "INSTA":      "📸 Instagram",
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
    total = len(EMOJI_POSITIONS)
    done = len(configured_keys)
    lines = [
        f"{HEADER}\n",
        f"🎨 <b>Emoji Setup</b>  ·  {done}/{total} configured\n",
        "Tap a button below to assign a premium emoji.\n",
    ]
    for key, label in EMOJI_POSITIONS.items():
        if key in configured_keys:
            lines.append(f"  ✅  {label}")
        else:
            lines.append(f"  ○  {label}")
    return "\n".join(lines)


def format_assign_prompt(label: str) -> str:
    return (
        f"{HEADER}\n\n"
        f"🎨 <b>Assign Emoji</b>\n\n"
        f"Send a premium or standard emoji for:\n\n"
        f"  →  <b>{label}</b>\n\n"
        f"<i>Send a Telegram premium custom emoji or a regular emoji</i>"
    )


def format_assign_updated() -> str:
    return f"{HEADER}\n\n✅ <b>Emoji Updated</b>"


# ─── Stats ────────────────────────────────────────────────────────────────────

async def format_stats(users: int, groups: int) -> str:
    star = await get_emoji_async("STAR")
    return _h(
        f"{star} <b>Bot Stats</b>\n\n"
        f"Users  ·  {users:,}\n"
        f"Groups  ·  {groups:,}"
    )


# ─── Legacy compat ────────────────────────────────────────────────────────────

async def format_user_info(user: User) -> str:
    """Legacy compat — returns user info panel"""
    return await format_myinfo(user)


async def format_download_complete(user: User) -> str:
    """Legacy compat — delivered confirmation with quoted mention"""
    emoji = await get_emoji_async("SUCCESS")
    safe_name = _escape((user.first_name or "User")[:32])
    raw = f'{emoji} Delivered  ·  "<a href="tg://user?id={user.id}">{safe_name}</a>"'
    return safe_caption(raw)


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
