"""
Global Log Channel — sends download activity to the dedicated log channel.

Usage:
    from utils.log_channel import log_download

    await log_download(
        user=message.from_user,
        link="https://...",
        chat=message.chat,          # pass the full chat object
        media_type="Video",
        time_taken=3.2,
    )

Rules:
- Never blocks main flow
- Never crashes if log fails
- Wrapped in try/except — silently ignored on failure
- Bot must be admin in LOG_CHANNEL_ID

Log format:
    📥 𝐃ᴏᴡɴʟᴏᴀᴅᴇʀ 𝐁ᴏᴛ 𝐋ᴏɢ 𝐂ʜᴀɴɴᴇʟ

    User:
    <a href="tg://user?id=USER_ID">Full Name</a>

    Link:
    https://...

    Chat:
    <a href="https://t.me/username">Group Name</a>  (or "Private" / group title)

    Media Type:
    Video / Audio / Playlist

    Time Taken:
    3.2s
"""
from __future__ import annotations

import html
from typing import Optional, Any

from core.config import LOG_CHANNEL_ID, LOG_CHANNEL_LINK
from utils.logger import logger


def _build_user_mention(user: Any) -> str:
    """Build a clickable HTML user mention — properly HTML-escaped."""
    user_id = getattr(user, "id", 0)
    first_name = (getattr(user, "first_name", None) or "User")[:32]
    last_name = (getattr(user, "last_name", None) or "").strip()
    full_name = f"{first_name} {last_name}".strip()[:48]
    # html.escape handles &, <, >, " — all characters that break HTML parsing
    safe_name = html.escape(full_name, quote=True)
    return f'<a href="tg://user?id={user_id}">{safe_name}</a>'


def _build_chat_display(chat: Any) -> str:
    """
    Build a chat display string.

    - Private chat → "Private"
    - Public group/channel (has username) → clickable link
    - Private group (no username) → plain title
    """
    if chat is None:
        return "Unknown"

    chat_type = getattr(chat, "type", "private")

    if chat_type == "private":
        return "Private"

    title = (getattr(chat, "title", None) or "Group")[:64]
    safe_title = html.escape(title, quote=True)
    username = getattr(chat, "username", None)

    if username:
        return f'<a href="https://t.me/{username}">{safe_title}</a>'

    return safe_title


async def log_download(
    user: Any,
    link: str,
    media_type: str,
    time_taken: float,
    chat: Any = None,
    # Legacy compat: accept chat_type string if chat object not available
    chat_type: Optional[str] = None,
) -> None:
    """
    Send a download log entry to the log channel.

    Parameters
    ----------
    user        : aiogram User object (or any object with .id, .first_name)
    link        : The URL that was downloaded
    media_type  : "Video" / "Audio" / "Playlist" / etc.
    time_taken  : Seconds elapsed for the download
    chat        : aiogram Chat object (preferred — enables clickable group links)
    chat_type   : Legacy fallback string "Group" or "Private" (used if chat=None)
    """
    try:
        # Import bot lazily to avoid circular imports
        from core.bot import bot

        user_mention = _build_user_mention(user)

        # Determine chat display
        if chat is not None:
            chat_display = _build_chat_display(chat)
        elif chat_type:
            chat_display = chat_type
        else:
            chat_display = "Unknown"

        # Truncate link for display (keep full URL, just cap at 300 chars)
        # html.escape prevents malformed URLs from breaking the HTML parser
        display_link = html.escape(link[:300] if len(link) > 300 else link, quote=False)

        text = (
            "📥 𝐃ᴏᴡɴʟᴏᴀᴅᴇʀ 𝐁ᴏᴛ 𝐋ᴏɢ 𝐂ʜᴀɴɴᴇʟ\n\n"
            f"User:\n{user_mention}\n\n"
            f"Link:\n{display_link}\n\n"
            f"Chat:\n{chat_display}\n\n"
            f"Media Type:\n{media_type}\n\n"
            f"Time Taken:\n{time_taken:.1f}s"
        )

        await bot.send_message(
            LOG_CHANNEL_ID,
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    except Exception:
        # Silently ignore — logging must never crash the bot
        pass
