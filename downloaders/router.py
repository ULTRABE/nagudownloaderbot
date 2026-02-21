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
    format_help,
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
    format_assign_menu,
    format_assign_prompt,
    format_assign_updated,
    format_stats,
    EMOJI_POSITIONS,
    code_panel,
    mono,
    safe_caption,
    _escape as _html_escape,
)
from ui.emoji_config import get_emoji_async
from utils.logger import logger
from utils.broadcast import (
    register_user,
    register_group,
    get_all_users,
    get_all_groups,
    run_broadcast,
)
from utils.redis_client import redis_client
from utils.log_channel import log_download

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
                _err = await get_emoji_async("ERROR")
                await msg.reply(
                    f"{_err} Unable to process this link.\n\nPlease try again.",
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
        if "message to be replied not found" in err_str or "replied message not found" in err_str:
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

    # Check if this is a first-time start
    is_first_time = not await user_state_manager.has_started_bot(m.from_user.id)

    await user_state_manager.mark_user_started(m.from_user.id)
    await user_state_manager.mark_user_unblocked(m.from_user.id)

    if m.chat.type == "private":
        await register_user(m.from_user.id)

    # First-time welcome — extra warm greeting
    if is_first_time:
        first_name = (m.from_user.first_name or "there")[:32]
        safe_name = _html_escape(first_name)
        _wave = await get_emoji_async("WAVE")
        _complete = await get_emoji_async("COMPLETE")
        first_time_msg = (
            f"{_wave} <b>Hey {safe_name}, welcome to Nagu Downloader!</b>\n\n"
            f"𝐓𝐡𝐚𝐧𝐤𝐬 𝐟𝐨𝐫 𝐬𝐭𝐚𝐫𝐭𝐢𝐧𝐠 𝐭𝐡𝐞 𝐛𝐨𝐭! {_complete}\n\n"
            "You're all set to receive music, videos and playlists directly here.\n\n"
            "ꜱᴇɴᴅ ᴀɴʏ ʟɪɴᴋ ꜰʀᴏᴍ:\n"
            "• YouTube — Videos, Shorts, Music\n"
            "• Spotify — Tracks &amp; Playlists\n"
            "• Instagram — Reels &amp; Posts\n"
            "• Pinterest — Video Pins"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➕ Add to Group", url=f"https://t.me/{(await bot.get_me()).username}?startgroup=true"),
            InlineKeyboardButton(text="📊 Status", callback_data="status"),
        ]])
        picture_path = Path("assets/picture.png")
        if picture_path.exists():
            try:
                await m.reply_photo(
                    FSInputFile(picture_path),
                    caption=first_time_msg,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                return
            except Exception as e:
                logger.error(f"Failed to send start image: {e}")
        await _safe_reply(m, first_time_msg, parse_mode="HTML", reply_markup=keyboard)
        return

    caption = await format_welcome(m.from_user, m.from_user.id)

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
    """Help — single unified message"""
    logger.info(f"HELP: User {m.from_user.id}")
    await _safe_reply(m, await format_help(), parse_mode="HTML")


# ─── /mp3 ────────────────────────────────────────────────────────────────────

@dp.message(Command("mp3"))
async def cmd_mp3(m: Message):
    """Extract audio from replied video as 192k MP3"""
    logger.info(f"MP3: User {m.from_user.id}")

    # Must reply to a video
    reply = m.reply_to_message
    if not reply or not reply.video:
        _info = await get_emoji_async("INFO")
        await _safe_reply(m, f"{_info} 𝐑𝐞𝐩𝐥𝐲 ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ᴡɪᴛʜ /mp3", parse_mode="HTML")
        return

    import tempfile
    from pathlib import Path
    from aiogram.types import FSInputFile
    from utils.media_processor import _run_ffmpeg

    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"

    # Progress bar helper
    def _bar(pct: int) -> str:
        width = 10
        filled = int(width * pct / 100)
        return f"[{'█' * filled}{'░' * (width - filled)}] {pct}%"

    progress = await _safe_reply(m, _bar(20), parse_mode="HTML")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            video_path = tmp / "input_video"

            # Download the video file
            try:
                await progress.edit_text(_bar(40), parse_mode="HTML")
            except Exception:
                pass

            file_info = await bot.get_file(reply.video.file_id)
            await bot.download_file(file_info.file_path, destination=str(video_path))

            try:
                await progress.edit_text(_bar(60), parse_mode="HTML")
            except Exception:
                pass

            # Extract audio as 192k MP3
            audio_path = tmp / "output_audio.mp3"
            args = [
                "-y", "-i", str(video_path),
                "-vn",
                "-acodec", "libmp3lame",
                "-b:a", "192k",
                "-threads", "4",
                str(audio_path),
            ]
            rc, err = await _run_ffmpeg(args)

            if rc != 0 or not audio_path.exists():
                try:
                    await progress.delete()
                except Exception:
                    pass
                _err = await get_emoji_async("ERROR")
                await _safe_reply(m, f"{_err} Unable to extract audio.\n\nPlease try again.", parse_mode="HTML")
                return

            try:
                await progress.edit_text(_bar(90), parse_mode="HTML")
            except Exception:
                pass

            # Send audio — use safe_caption to prevent ENTITY_TEXT_INVALID
            safe_name = _html_escape(first_name[:32])
            success_emoji = await get_emoji_async("SUCCESS")
            caption = safe_caption(
                f'{success_emoji} Delivered — <a href="tg://user?id={user_id}">{safe_name}</a>'
            )
            t_start = time.monotonic()
            try:
                await bot.send_audio(
                    m.chat.id,
                    FSInputFile(audio_path),
                    caption=caption,
                    parse_mode="HTML",
                )
            except Exception as _send_err:
                _err_str = str(_send_err).lower()
                if "entity_text_invalid" in _err_str or "bad request" in _err_str:
                    logger.warning(f"MP3 send_audio: ENTITY_TEXT_INVALID, retrying without caption")
                    await bot.send_audio(
                        m.chat.id,
                        FSInputFile(audio_path),
                    )
                else:
                    raise
            elapsed = time.monotonic() - t_start

            # Delete progress
            try:
                await progress.delete()
            except Exception:
                pass

            logger.info(f"MP3: Sent to {user_id}")

            # Log to channel
            asyncio.create_task(log_download(
                user=m.from_user,
                link="[MP3 extraction]",
                chat=m.chat,
                media_type="Audio (MP3)",
                time_taken=elapsed,
            ))

    except Exception as e:
        logger.error(f"MP3 ERROR: {e}", exc_info=True)
        try:
            await progress.delete()
        except Exception:
            pass
        _err = await get_emoji_async("ERROR")
        await _safe_reply(m, f"{_err} Unable to extract audio.\n\nPlease try again.", parse_mode="HTML")


# ─── /ping ────────────────────────────────────────────────────────────────────

@dp.message(Command("ping"))
async def cmd_ping(m: Message):
    """Health check — anyone can use"""
    t0 = time.monotonic()
    _ping = await get_emoji_async("PING")
    try:
        sent = await m.reply(f"{_ping} Pong...", parse_mode="HTML")
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        try:
            await sent.edit_text(
                f"{_ping} Pong — <b>{elapsed_ms} ms</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        try:
            await bot.send_message(
                m.chat.id,
                f"{_ping} Pong — <b>{elapsed_ms} ms</b>",
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
    await _safe_reply(m, await format_id(user, label), parse_mode="HTML")


# ─── /chatid ──────────────────────────────────────────────────────────────────

@dp.message(Command("chatid"))
async def cmd_chatid(m: Message):
    chat_title = (m.chat.title or "Private Chat")[:20]
    await _safe_reply(
        m,
        await format_chatid(m.chat.id, chat_title, m.chat.type),
        parse_mode="HTML",
    )


# ─── /myinfo ──────────────────────────────────────────────────────────────────

@dp.message(Command("myinfo"))
async def cmd_myinfo(m: Message):
    chat_title = (m.chat.title or "Private")[:20]
    await _safe_reply(
        m,
        await format_myinfo(m.from_user, chat_title),
        parse_mode="HTML",
    )


# ─── /status ──────────────────────────────────────────────────────────────────

@dp.message(Command("status"))
async def cmd_status(m: Message):
    uptime_secs = int(time.time() - _BOT_START_TIME)
    days = uptime_secs // 86400
    hours = (uptime_secs % 86400) // 3600
    uptime_str = f"{days}d {hours}h"

    if _is_admin(m.from_user.id):
        # Admin: full system stats
        await _safe_reply(
            m,
            await format_status(active_jobs=0, queue=0, uptime=uptime_str),
            parse_mode="HTML",
        )
    else:
        # Normal user: uptime + active jobs only (no system internals)
        _info = await get_emoji_async("INFO")
        await _safe_reply(
            m,
            f"{_info} <b>𝐁𝐨𝐭 𝐒𝐭𝐚𝐭𝐮𝐬</b>\n\nUptime: {uptime_str}\nActive Jobs: 0",
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
            await format_status(active_jobs=0, queue=0, uptime=uptime_str),
            parse_mode="HTML",
        )
    except Exception:
        try:
            await bot.send_message(
                callback.message.chat.id,
                await format_status(active_jobs=0, queue=0, uptime=uptime_str),
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
        _err = await get_emoji_async("ERROR")
        await _safe_reply(m, f"{_err} 𝐀ᴅᴍɪɴ 𝐎ɴʟʏ", parse_mode="HTML")
        return
    users  = await get_all_users()
    groups = await get_all_groups()
    stats  = {"users": len(users), "groups": len(groups)}
    await _safe_reply(m, await format_admin_panel(stats), parse_mode="HTML")


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
            await format_status(active_jobs=0, queue=0, uptime=f"{days}d {hours}h"),
            parse_mode="HTML",
        )
        return

    users  = await get_all_users()
    groups = await get_all_groups()
    await _safe_reply(m, await format_stats(len(users), len(groups)), parse_mode="HTML")


@dp.message(Command("broadcast"))
async def cmd_broadcast(m: Message):
    """
    Broadcast to all users + groups. Admin only.

    Usage:
      /broadcast <text>          — broadcast text message
      /broadcast (reply to msg) — broadcast that exact message (any type)
    """
    if not _is_admin(m.from_user.id):
        _err = await get_emoji_async("ERROR")
        await _safe_reply(m, f"{_err} 𝐀ᴅᴍɪɴ 𝐎ɴʟʏ", parse_mode="HTML")
        return

    # If replying to a message — broadcast that message (any media type)
    if m.reply_to_message:
        reply = m.reply_to_message
        logger.info(f"BROADCAST: Admin {m.from_user.id} broadcasting replied message")
        await _safe_reply(m, await format_broadcast_started(), parse_mode="HTML")
        asyncio.create_task(
            run_broadcast(bot, m.from_user.id, reply_to_msg=reply)
        )
        return

    # Otherwise broadcast text from command
    parts = (m.text or "").split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        _info = await get_emoji_async("INFO")
        await _safe_reply(
            m,
            f"{_info} 𝐁ʀᴏᴀᴅᴄᴀꜱᴛ 𝐔ꜱᴀɢᴇ\n\n"
            "/broadcast Your message here\n\n"
            "Or reply to any message with /broadcast to broadcast it.",
            parse_mode="HTML",
        )
        return

    broadcast_text = parts[1].strip()
    logger.info(f"BROADCAST: Admin {m.from_user.id} starting text broadcast: {broadcast_text[:50]}")

    await _safe_reply(m, await format_broadcast_started(), parse_mode="HTML")

    asyncio.create_task(
        run_broadcast(bot, m.from_user.id, text=broadcast_text)
    )


@dp.message(Command("broadcast_media"))
async def cmd_broadcast_media(m: Message):
    """Broadcast media (reply to media). Admin only. Legacy — use /broadcast instead."""
    if not _is_admin(m.from_user.id):
        _err = await get_emoji_async("ERROR")
        await _safe_reply(m, f"{_err} 𝐀ᴅᴍɪɴ 𝐎ɴʟʏ", parse_mode="HTML")
        return

    if not m.reply_to_message:
        _info = await get_emoji_async("INFO")
        await _safe_reply(m, f"{_info} Reply to a media message to broadcast it.", parse_mode="HTML")
        return

    reply = m.reply_to_message
    has_media = any([
        reply.photo, reply.video, reply.audio,
        reply.document, reply.animation, reply.voice,
        reply.sticker,
    ])

    if not has_media and not reply.text:
        _info = await get_emoji_async("INFO")
        await _safe_reply(m, f"{_info} Reply to a message with media or text.", parse_mode="HTML")
        return

    await _safe_reply(m, await format_broadcast_started(), parse_mode="HTML")

    asyncio.create_task(
        run_broadcast(bot, m.from_user.id, reply_to_msg=reply)
    )


# ─── /assign — Visual emoji assignment system ─────────────────────────────────

# Redis key prefix for emoji assignments
_EMOJI_KEY_PREFIX = "emoji:"

# In-memory pending assignment state: user_id → emoji_key
_assign_pending: dict = {}


async def _get_configured_emoji_keys() -> set:
    """Get set of emoji keys that have been configured in Redis"""
    configured = set()
    for key in EMOJI_POSITIONS.keys():
        redis_key = f"{_EMOJI_KEY_PREFIX}{key}"
        val = await redis_client.get(redis_key)
        if val:
            configured.add(key)
    return configured


async def _build_assign_keyboard(configured_keys: set) -> InlineKeyboardMarkup:
    """Build inline keyboard for emoji assignment menu"""
    rows = []
    for key, label in EMOJI_POSITIONS.items():
        action = "Change" if key in configured_keys else "Set"
        rows.append([
            InlineKeyboardButton(
                text=f"{action} {label}",
                callback_data=f"assign:{key}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(Command("assign"))
async def cmd_assign(m: Message):
    """Visual emoji assignment system — admin only"""
    if not _is_admin(m.from_user.id):
        _err = await get_emoji_async("ERROR")
        await _safe_reply(m, f"{_err} 𝐀ᴅᴍɪɴ 𝐎ɴʟʏ", parse_mode="HTML")
        return

    configured = await _get_configured_emoji_keys()
    keyboard = await _build_assign_keyboard(configured)
    menu_text = format_assign_menu(configured)
    await _safe_reply(m, menu_text, reply_markup=keyboard, parse_mode="HTML")


@dp.callback_query(lambda c: c.data and c.data.startswith("assign:"))
async def cb_assign(callback):
    """Handle emoji assignment button tap"""
    if not _is_admin(callback.from_user.id):
        await callback.answer("Admin Only", show_alert=True)
        return

    key = callback.data.split(":", 1)[1]
    if key not in EMOJI_POSITIONS:
        await callback.answer("Invalid position.", show_alert=True)
        return

    label = EMOJI_POSITIONS[key]
    await callback.answer()

    # Store pending assignment
    _assign_pending[callback.from_user.id] = key

    try:
        await callback.message.reply(
            format_assign_prompt(label),
            parse_mode="HTML",
        )
    except Exception:
        try:
            await bot.send_message(
                callback.message.chat.id,
                format_assign_prompt(label),
                parse_mode="HTML",
            )
        except Exception:
            pass


@dp.message(lambda m: m.from_user and m.from_user.id in _assign_pending)
async def handle_assign_emoji(m: Message):
    """
    Receive emoji for assignment.

    Accepts:
    1. Message with custom_emoji entity (premium Telegram emoji)
       → stores custom_emoji_id (numeric string) in Redis
    2. Message with a plain unicode emoji in text
       → stores the unicode character in Redis

    Does NOT require stickers.
    Does NOT use file_id.
    """
    if not _is_admin(m.from_user.id):
        return

    # Only process if this user has a pending assignment
    if m.from_user.id not in _assign_pending:
        return

    key = _assign_pending.pop(m.from_user.id, None)
    if not key or key not in EMOJI_POSITIONS:
        return

    emoji_value: str | None = None

    # Priority 1: custom_emoji entity (premium Telegram emoji)
    if m.entities:
        for entity in m.entities:
            if entity.type == "custom_emoji" and entity.custom_emoji_id:
                emoji_value = entity.custom_emoji_id  # numeric ID string
                break

    # Priority 2: plain unicode emoji in text
    if not emoji_value and m.text:
        text = m.text.strip()
        if text:
            emoji_value = text[:8]  # store first 8 chars (covers multi-char emoji)

    if not emoji_value:
        await _safe_reply(
            m,
            "⚠ No emoji detected. Send a premium emoji or a standard emoji character.",
            parse_mode="HTML",
        )
        # Restore pending state so admin can try again
        _assign_pending[m.from_user.id] = key
        return

    redis_key = f"{_EMOJI_KEY_PREFIX}{key}"
    await redis_client.set(redis_key, emoji_value)

    label = EMOJI_POSITIONS[key]
    logger.info(f"ASSIGN: Admin {m.from_user.id} set {key} = {emoji_value[:30]}")

    await _safe_reply(m, format_assign_updated(), parse_mode="HTML")

    # Refresh the assign menu
    await asyncio.sleep(0.3)
    configured = await _get_configured_emoji_keys()
    keyboard = await _build_assign_keyboard(configured)
    menu_text = format_assign_menu(configured)
    try:
        await bot.send_message(
            m.chat.id,
            menu_text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    except Exception:
        pass


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


# ─── Universal link routing ───────────────────────────────────────────────────

async def _route_url(m: Message, url: str) -> None:
    """Route a URL to the appropriate downloader."""
    url_lower = url.lower()

    # Register group
    if m.chat.type in ("group", "supergroup"):
        await register_group(m.chat.id)

    # Delete user's link message after 5 seconds (except Spotify playlists)
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
            "youtu.be" in url_lower
        ):
            await handle_youtube(m, url)
        elif "pinterest.com" in url_lower or "pin.it" in url_lower:
            await handle_pinterest(m, url)
        elif "spotify.com" in url_lower or url_lower.startswith("spotify:"):
            await handle_spotify_playlist(m, url)
        else:
            _err = await get_emoji_async("ERROR")
            await _safe_reply(
                m,
                f"{_err} Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error handling link: {e}", exc_info=True)
        try:
            _err = await get_emoji_async("ERROR")
            await _safe_reply(
                m,
                f"{_err} Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
        except Exception:
            pass


@dp.message(F.text.regexp(LINK_RE))
async def handle_link(m: Message):
    """Route incoming text links to appropriate downloader"""
    match = LINK_RE.search(m.text or "")
    if not match:
        return
    url = match.group(0).strip()
    logger.info(f"LINK: {url[:60]} from {m.from_user.id}")
    await _route_url(m, url)


@dp.message(F.caption.regexp(LINK_RE))
async def handle_caption_link(m: Message):
    """Route links found in message captions (forwarded messages, etc.)"""
    match = LINK_RE.search(m.caption or "")
    if not match:
        return
    url = match.group(0).strip()
    logger.info(f"LINK (caption): {url[:60]} from {m.from_user.id}")
    await _route_url(m, url)


@dp.message()
async def fallback_handler(m: Message):
    """
    Catch-all fallback — silently ignores non-link messages.
    Prevents 'Update not handled' flood in logs.
    """
    # Only log if it looks like a link attempt (has http but didn't match)
    text = m.text or m.caption or ""
    if text and ("http" in text.lower() or "spotify:" in text.lower()):
        logger.debug(f"Fallback: unmatched message from {m.from_user.id}: {text[:60]}")


def register_download_handlers():
    """Register download handlers — called from main"""
    logger.info("Download handlers registered")
