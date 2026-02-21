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
        ✓ Delivered — <Name>

    - Escapes all user-provided text (first_name)
    - Uses HTML parse_mode only
    - Passes through safe_caption() for final length/tag check
    - Never raises — returns plain fallback on any error
    """
    try:
        safe_name = _escape((first_name or "User")[:32])
        raw = f'{delivered_emoji} Delivered — <a href="tg://user?id={user_id}">{safe_name}</a>'
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
    """
    Returns a clean delivered caption with clickable user mention.
    Output: ✓ Delivered — <Name>

    Uses html.escape() on the display name so that characters like & " ' < >
    in the user's first name cannot break Telegram's HTML parser and cause
    ENTITY_TEXT_INVALID errors.
    """
    emoji = await get_emoji_async("DELIVERED")
    # html.escape handles &, <, >, " — all characters that break HTML parsing
    safe_name = _escape((first_name or "User")[:32])
    raw = f'{emoji} Delivered — <a href="tg://user?id={user_id}">{safe_name}</a>'
    return safe_caption(raw)


def format_delivered_with_mention_sync(user_id: int, first_name: str) -> str:
    """Sync fallback for format_delivered_with_mention."""
    emoji = get_emoji("DELIVERED")
    safe_name = _escape((first_name or "User")[:32])
    raw = f'{emoji} Delivered — <a href="tg://user?id={user_id}">{safe_name}</a>'
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

    return (
        "◇—◇ <b>𝐍𝐀𝐆𝐔 𝐃𝐎𝐖𝐍𝐋𝐎𝐀𝐃𝐄𝐑 𝐁𝐎𝐓</b> ◇—◇\n\n"
        f"{zap} <b>Fast &amp; Powerful Media Downloader</b>\n\n"
        "Download videos &amp; audio from:\n\n"
        f"{yt} YouTube\n"
        f"{ig} Instagram\n"
        f"{sp} Spotify\n"
        f"{pin} Pinterest\n\n"
        "Paste a link and I'll handle the rest."
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

    # Row 1: Download | Status
    rows.append([
        InlineKeyboardButton(text="📥 Download", callback_data="cb_download"),
        InlineKeyboardButton(text="📊 Status",   callback_data="status"),
    ])

    # Row 2: Help | Settings
    rows.append([
        InlineKeyboardButton(text="📜 Help",     callback_data="cb_help"),
        InlineKeyboardButton(text="⚙ Settings",  callback_data="cb_settings"),
    ])

    # Row 3: Updates | Support (only if configured)
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
    username = f"@{_escape(user.username)}" if user.username else "—"
    chat_type = "private" if not chat_title else "group"
    safe_name = _escape((user.first_name or "—")[:32])
    user_link = f'<a href="tg://user?id={user.id}">{safe_name}</a>'
    return _h(
        f"{user_emoji} 𝐀ᴄᴄᴏᴜɴᴛ 𝐈ɴꜰᴏ\n\n"
        f"𝐍ᴀᴍᴇ: {user_link}\n"
        f"𝐋ᴀꜱᴛ 𝐍ᴀᴍᴇ: {_escape((user.last_name or '—')[:32])}\n"
        f"𝐔ꜱᴇʀɴᴀᴍᴇ: {username}\n"
        f"𝐈ᴅ: <code>{user.id}</code>\n"
        f"𝐋ᴀɴɢᴜᴀɢᴇ: {_escape(user.language_code or '—')}\n"
        f"𝐂ʜᴀᴛ 𝐓ʏᴘᴇ: {chat_type}"
    )


# ─── /id ──────────────────────────────────────────────────────────────────────

async def format_id(user: User, label: str = "YOUR  ID") -> str:
    """User ID info"""
    id_emoji = await get_emoji_async("ID")
    username = f"@{_escape(user.username)}" if user.username else "—"
    is_other = "USER" in label.upper()
    title = "𝐔ꜱᴇʀ 𝐈ᴅ" if is_other else "𝐘ᴏᴜʀ 𝐈ᴅ"
    safe_name = _escape((user.first_name or "—")[:32])
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
    safe_name = _escape((user.first_name or "User")[:32])
    user_link = f'<a href="tg://user?id={user.id}">{safe_name}</a>'
    name_short = _escape((name or "Playlist")[:30])
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
    safe_name = _escape((user.first_name or "User")[:32])
    raw = f'{emoji} Delivered — <a href="tg://user?id={user.id}">{safe_name}</a>'
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
