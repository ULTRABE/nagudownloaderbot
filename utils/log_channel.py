"""
Global Log Channel — sends download activity to the dedicated log channel.

Usage:
    from utils.log_channel import log_download

    await log_download(
        user=message.from_user,
        link="https://...",
        chat_type="Group",
        media_type="Video",
        time_taken=3.2,
    )

Rules:
- Never blocks main flow
- Never crashes if log fails
- Wrapped in try/except — silently ignored on failure
- Bot must be admin in LOG_CHANNEL_ID
"""
from __future__ import annotations

import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram.types import User

from core.config import LOG_CHANNEL_ID, LOG_CHANNEL_LINK
from utils.logger import logger


async def log_download(
    user,
    link: str,
    chat_type: str,
    media_type: str,
    time_taken: float,
) -> None:
    """
    Send a download log entry to the log channel.

    Parameters
    ----------
    user        : aiogram User object (or any object with .id and .first_name)
    link        : The URL that was downloaded
    chat_type   : "Group" or "Private"
    media_type  : "Video" / "Audio" / "Playlist" / etc.
    time_taken  : Seconds elapsed for the download
    """
    try:
        # Import bot lazily to avoid circular imports
        from core.bot import bot

        user_id = getattr(user, "id", 0)
        first_name = (getattr(user, "first_name", None) or "User")[:32]
        safe_name = first_name.replace("<", "").replace(">", "")
        user_mention = f'<a href="tg://user?id={user_id}">{safe_name}</a>'

        # Truncate link for display
        display_link = link[:200] if len(link) > 200 else link

        text = (
            "📥 𝐃ᴏᴡɴʟᴏᴀᴅᴇʀ 𝐁ᴏᴛ 𝐋ᴏɢ 𝐂ʜᴀɴɴᴇʟ\n\n"
            f"User:\n{user_mention}\n\n"
            f"Link:\n{display_link}\n\n"
            f"Chat Type:\n{chat_type}\n\n"
            f"Media Type:\n{media_type}\n\n"
            f"Time Taken:\n{time_taken:.1f}s\n\n"
            f"Channel:\n{LOG_CHANNEL_LINK}"
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
