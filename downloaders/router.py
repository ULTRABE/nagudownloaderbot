"""
Download router — Routes URLs to handlers, admin commands.

Design:
  - All media replies quote the original message (reply_to_message_id)
  - Fallback to plain send if original message was deleted
  - Caption: ✓ Delivered — <mention>
  - Group registration on bot join
  - Broadcast: admin-only, background, with pin
  - Global error handler middleware — never crash polling
"""
import asyncio
import re
import time
import traceback
from pathlib import Path

from aiogram import F
from aiogram.types import (
    Message, FSInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters import CommandStart, Command

# ErrorEvent is available in aiogram 3.x for the @dp.errors() handler
try:
    from aiogram.types import ErrorEvent
except ImportError:
    ErrorEvent = None  # type: ignore

from core.bot import dp, bot
from core.config import config
from downloaders.instagram import handle_instagram
from downloaders.pinterest import handle_pinterest
from downloaders.youtube import handle_youtube
from downloaders.spotify import handle_spotify_playlist
from ui.formatting import (
    format_welcome,
    format_help_video,
    format_help_music,
    format_help_info,
    format_admin_panel,
    format_id,
    format_chatid,
    format_myinfo,
    format_status,
    format_broadcast_started,
    format_broadcast_report,
    code_panel,
    mono,
)
from utils.logger import logger
from utils.broadcast import (
    register_user,
    register_group,
    get_all_users,
    get_all_groups,
    run_broadcast,
)

# Link regex — improved to catch more URL formats
LINK_RE = re.compile(r"https?://[^\s<>\"']+")

# Bot start time for uptime calculation
_BOT_START_TIME = time.time()

# ─── Global error handler middleware ─────────────────────────────────────────

@dp.errors()
async def global_error_handler(event: ErrorEvent) -> bool:
    """
    Global error handler — catches all unhandled exceptions.
    Logs full traceback. Never crashes polling.
    Returns True to suppress the exception.
    """
    exception = event.exception
    update = event.update
    tb = traceback.format_exc()
    logger.error(
        f"Unhandled exception in update {getattr(update, 'update_id', '?')}: "
        f"{type(exception).__name__}: {exception}\n{tb}"
    )
    # Try to notify user if possible
    try:
        msg = getattr(update, "message", None)
        cb = getattr(update, "callback_query", None)
        if msg:
            try:
                await msg.reply(
                    "⚠ Unable to process this link.\n\nPlease try again.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        elif cb:
            try:
                await cb.answer(
                    "Something went wrong. Please try again.",
                    show_alert=True,
                )
            except Exception:
                pass
    except Exception:
        pass
    return True  # Suppress exception — keep polling alive

# ─── Safe reply helper ────────────────────────────────────────────────────────

async def _safe_reply(m: Message, text: str, **kwargs) -> None:
    """Reply with fallback to plain send if original message was deleted."""
    try:
        await m.reply(text, **kwargs)
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "bad request" in err_str:
            try:
                await bot.send_message(m.chat.id, text, **kwargs)
            except Exception:
                pass
        else:
            logger.error(f"Reply failed: {e}")

# ─── /start ───────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def start_command(m: Message):
    """Start command — register user, show welcome"""
    logger.info(f"START: User {m.from_user.id}")

    from utils.user_state import user_state_manager
    await user_state_manager.mark_user_started(m.from_user.id)
    await user_state_manager.mark_user_unblocked(m.from_user.id)

    if m.chat.type == "private":
        await register_user(m.from_user.id)

    caption = format_welcome(m.from_user, m.from_user.id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➕ Add to Group", url=f"https://t.me/{(await bot.get_me()).username}?startgroup=true"),
        InlineKeyboardButton(text="📊 Status", callback_data="status"),
    ]])

    picture_path = Path("assets/picture.png")
    if picture_path.exists():
        try:
            await m.reply_photo(
                FSInputFile(picture_path),
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            return
        except Exception as e:
            logger.error(f"Failed to send start image: {e}")

    await _safe_reply(m, caption, parse_mode="HTML", reply_markup=keyboard)


# ─── /help ────────────────────────────────────────────────────────────────────

@dp.message(Command("help"))
async def help_command(m: Message):
    """Help — three sections"""
    logger.info(f"HELP: User {m.from_user.id}")
    await _safe_reply(m, format_help_video(), parse_mode="HTML")
    await asyncio.sleep(0.15)
    await _safe_reply(m, format_help_music(), parse_mode="HTML")
    await asyncio.sleep(0.15)
    await _safe_reply(m, format_help_info(), parse_mode="HTML")


# ─── /ping ────────────────────────────────────────────────────────────────────

@dp.message(Command("ping"))
async def cmd_ping(m: Message):
    """Health check — anyone can use"""
    t0 = time.monotonic()
    try:
        sent = await m.reply("🏓 Pong...", parse_mode="HTML")
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        try:
            await sent.edit_text(
                f"🏓 Pong — <b>{elapsed_ms} ms</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        try:
            await bot.send_message(
                m.chat.id,
                f"🏓 Pong — <b>{elapsed_ms} ms</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─── /id ──────────────────────────────────────────────────────────────────────

@dp.message(Command("id"))
async def cmd_id(m: Message):
    if m.reply_to_message:
        user = m.reply_to_message.from_user
        label = "USER  ID"
    else:
        user = m.from_user
        label = "YOUR  ID"
    await _safe_reply(m, format_id(user, label), parse_mode="HTML")


# ─── /chatid ──────────────────────────────────────────────────────────────────

@dp.message(Command("chatid"))
async def cmd_chatid(m: Message):
    chat_title = (m.chat.title or "Private Chat")[:20]
    await _safe_reply(
        m,
        format_chatid(m.chat.id, chat_title, m.chat.type),
        parse_mode="HTML",
    )


# ─── /myinfo ──────────────────────────────────────────────────────────────────

@dp.message(Command("myinfo"))
async def cmd_myinfo(m: Message):
    chat_title = (m.chat.title or "Private")[:20]
    await _safe_reply(
        m,
        format_myinfo(m.from_user, chat_title),
        parse_mode="HTML",
    )


# ─── /status ──────────────────────────────────────────────────────────────────

@dp.message(Command("status"))
async def cmd_status(m: Message):
    uptime_secs = int(time.time() - _BOT_START_TIME)
    days = uptime_secs // 86400
    hours = (uptime_secs % 86400) // 3600
    uptime_str = f"{days}d {hours}h"
    await _safe_reply(
        m,
        format_status(active_jobs=0, queue=0, uptime=uptime_str),
        parse_mode="HTML",
    )


@dp.callback_query(lambda c: c.data == "status")
async def cb_status(callback):
    uptime_secs = int(time.time() - _BOT_START_TIME)
    days = uptime_secs // 86400
    hours = (uptime_secs % 86400) // 3600
    uptime_str = f"{days}d {hours}h"
    await callback.answer()
    try:
        await callback.message.reply(
            format_status(active_jobs=0, queue=0, uptime=uptime_str),
            parse_mode="HTML",
        )
    except Exception:
        try:
            await bot.send_message(
                callback.message.chat.id,
                format_status(active_jobs=0, queue=0, uptime=uptime_str),
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─── Admin commands ───────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    result = config.is_admin(user_id)
    if not result:
        logger.debug(f"Admin check failed for user {user_id}. Configured admins: {config.ADMIN_IDS}")
    return result


@dp.message(Command("admin"))
async def cmd_admin(m: Message):
    if not _is_admin(m.from_user.id):
        await _safe_reply(m, "⛔ You are not authorized.", parse_mode="HTML")
        return
    users  = await get_all_users()
    groups = await get_all_groups()
    stats  = {"users": len(users), "groups": len(groups)}
    await _safe_reply(m, format_admin_panel(stats), parse_mode="HTML")


@dp.message(Command("stats"))
async def cmd_stats(m: Message):
    """Stats — admin only for full details"""
    if not _is_admin(m.from_user.id):
        # Non-admin: show minimal public stats
        uptime_secs = int(time.time() - _BOT_START_TIME)
        days = uptime_secs // 86400
        hours = (uptime_secs % 86400) // 3600
        await _safe_reply(
            m,
            format_status(active_jobs=0, queue=0, uptime=f"{days}d {hours}h"),
            parse_mode="HTML",
        )
        return

    users  = await get_all_users()
    groups = await get_all_groups()
    text = (
        "📊 <b>Bot Stats</b>\n\n"
        f"Users: {len(users)}\n"
        f"Groups: {len(groups)}"
    )
    await _safe_reply(m, text, parse_mode="HTML")


@dp.message(Command("broadcast"))
async def cmd_broadcast(m: Message):
    """Broadcast text to all users + groups. Admin only."""
    if not _is_admin(m.from_user.id):
        await _safe_reply(m, "⛔ You are not authorized.", parse_mode="HTML")
        return

    parts = m.text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await _safe_reply(
            m,
            "Usage: /broadcast Your message here",
            parse_mode="HTML",
        )
        return

    broadcast_text = parts[1].strip()
    logger.info(f"BROADCAST: Admin {m.from_user.id} starting broadcast: {broadcast_text[:50]}")

    await _safe_reply(m, format_broadcast_started(), parse_mode="HTML")

    asyncio.create_task(
        run_broadcast(bot, m.from_user.id, text=broadcast_text)
    )


@dp.message(Command("broadcast_media"))
async def cmd_broadcast_media(m: Message):
    """Broadcast media (reply to media). Admin only."""
    if not _is_admin(m.from_user.id):
        await _safe_reply(m, "⛔ You are not authorized.", parse_mode="HTML")
        return

    if not m.reply_to_message:
        await _safe_reply(m, "Reply to a media message to broadcast it.", parse_mode="HTML")
        return

    reply = m.reply_to_message
    has_media = any([
        reply.photo, reply.video, reply.audio,
        reply.document, reply.animation, reply.voice,
    ])

    if not has_media and not reply.text:
        await _safe_reply(m, "Reply to a message with media or text.", parse_mode="HTML")
        return

    await _safe_reply(m, format_broadcast_started(), parse_mode="HTML")

    asyncio.create_task(
        run_broadcast(bot, m.from_user.id, reply_to_msg=reply)
    )


# ─── Group registration ───────────────────────────────────────────────────────

@dp.message(F.new_chat_members)
async def on_bot_added_to_group(m: Message):
    """Register group when bot is added"""
    try:
        bot_me = await bot.get_me()
        for member in m.new_chat_members:
            if member.id == bot_me.id:
                await register_group(m.chat.id)
                logger.info(f"Registered group: {m.chat.id} ({m.chat.title})")
                break
    except Exception as e:
        logger.error(f"Group registration error: {e}")


# ─── Link handler ─────────────────────────────────────────────────────────────

@dp.message(F.text.regexp(LINK_RE))
async def handle_link(m: Message):
    """Route incoming links to appropriate downloader"""
    # Extract first URL from message
    match = LINK_RE.search(m.text or "")
    if not match:
        return
    url = match.group(0).strip()
    logger.info(f"LINK: {url[:60]} from {m.from_user.id}")

    # Register group
    if m.chat.type in ("group", "supergroup"):
        await register_group(m.chat.id)

    # Delete user's link message after 5 seconds (except Spotify playlists)
    url_lower = url.lower()
    is_spotify_playlist_link = (
        "spotify.com" in url_lower and
        ("/playlist/" in url_lower or "/album/" in url_lower)
    )
    if not is_spotify_playlist_link:
        async def _delete_link():
            await asyncio.sleep(5)
            try:
                await m.delete()
            except Exception:
                pass
        asyncio.create_task(_delete_link())

    try:
        if "instagram.com" in url_lower:
            await handle_instagram(m, url)
        elif (
            "youtube.com" in url_lower or
            "youtu.be" in url_lower or
            "music.youtube.com" in url_lower
        ):
            await handle_youtube(m, url)
        elif "pinterest.com" in url_lower or "pin.it" in url_lower:
            await handle_pinterest(m, url)
        elif "spotify.com" in url_lower:
            await handle_spotify_playlist(m, url)
        else:
            await _safe_reply(
                m,
                "⚠ Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error handling link: {e}", exc_info=True)
        try:
            await _safe_reply(
                m,
                "⚠ Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
        except Exception:
            pass


def register_download_handlers():
    """Register download handlers — called from main"""
    logger.info("Download handlers registered")
