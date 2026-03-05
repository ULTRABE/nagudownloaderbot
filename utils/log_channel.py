"""
Global Log Channel — logs every download to the dedicated log channel.

Format:
    📥 Download Log

    User  ·  "Name" · ID: 123456
    @username (or no username)

    Link  ·  https://...

    Chat  ·  Group Name
    Type  ·  Video (Instagram)
    Time  ·  3.2s

Rules:
- Never blocks main flow — fire-and-forget via asyncio.create_task
- Never crashes — silently ignored on failure
- Bot must be admin in LOG_CHANNEL_ID
- User is always clickable via tg://user?id=ID
- User ID is always shown explicitly
- Full link is always shown
"""
from __future__ import annotations

import html
from typing import Optional, Any

from core.config import LOG_CHANNEL_ID
from utils.logger import logger


def _build_user_section(user: Any) -> str:
    """
    Build user display with clickable mention + explicit ID.
    Works even if user has no username.
    """
    user_id = getattr(user, "id", 0)
    first_name = (getattr(user, "first_name", None) or "User")[:32]
    last_name = (getattr(user, "last_name", None) or "").strip()
    full_name = f"{first_name} {last_name}".strip()[:48]
    safe_name = html.escape(full_name, quote=True)
    username = getattr(user, "username", None)

    # Clickable mention + explicit ID (always visible)
    mention = f'"<a href="tg://user?id={user_id}">{safe_name}</a>"'
    line1 = f"User  ·  {mention}  ·  <code>{user_id}</code>"

    # Username line
    if username:
        line2 = f"@{html.escape(username)}"
    else:
        line2 = "<i>no username</i>"

    return f"{line1}\n{line2}"


def _build_chat_display(chat: Any) -> str:
    """Build chat display — clickable if public, plain if private."""
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
    chat_type: Optional[str] = None,
) -> None:
    """
    Send a download log entry to the log channel.
    Always shows: user mention, user ID, full link, chat, media type, time.
    """
    try:
        from core.bot import bot

        user_section = _build_user_section(user)

        # Chat display
        if chat is not None:
            chat_display = _build_chat_display(chat)
        elif chat_type:
            chat_display = chat_type
        else:
            chat_display = "Unknown"

        # Full link — escape HTML entities
        display_link = html.escape(link, quote=False)

        text = (
            f"📥 <b>Download Log</b>\n\n"
            f"{user_section}\n\n"
            f"Link  ·  {display_link}\n\n"
            f"Chat  ·  {chat_display}\n"
            f"Type  ·  {media_type}\n"
            f"Time  ·  {time_taken:.1f}s"
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
