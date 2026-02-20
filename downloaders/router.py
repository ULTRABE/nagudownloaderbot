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
)
from utils.logger import logger
from utils.broadcast import (
    register_user,
    register_group,
    get_all_users,
    get_all_groups,
    run_broadcast,
)
from utils.redis_client import redis_client

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

    # Check if this is a first-time start
    is_first_time = not await user_state_manager.has_started_bot(m.from_user.id)

    await user_state_manager.mark_user_started(m.from_user.id)
    await user_state_manager.mark_user_unblocked(m.from_user.id)

    if m.chat.type == "private":
        await register_user(m.from_user.id)

    # First-time welcome — extra warm greeting
    if is_first_time:
        first_name = (m.from_user.first_name or "there")[:32]
        safe_name = first_name.replace("<", "").replace(">", "")
        first_time_msg = (
            f"👋 <b>Hey {safe_name}, welcome to Nagu Downloader!</b>\n\n"
            "𝐓𝐡𝐚𝐧𝐤𝐬 𝐟𝐨𝐫 𝐬𝐭𝐚𝐫𝐭𝐢𝐧𝐠 𝐭𝐡𝐞 𝐛𝐨𝐭! 🎉\n\n"
            "You're all set to receive music, videos and playlists directly here.\n\n"
            "ꜱᴇɴᴅ ᴀɴʏ ʟɪɴᴋ ꜰʀᴏᴍ:\n"
            "• YouTube — Videos, Shorts, Music\n"
            "• Spotify — Tracks &amp; Playlists\n"
            "• Instagram — Reels &amp; Posts\n"
            "• Pinterest — Video Pins\n\n"
            "𝟦𝟢–𝟧𝟢 ᴍɪɴᴜᴛᴇꜱ+ ꜰᴀꜱᴛᴇʀ ᴅᴏᴡɴʟᴏᴀᴅꜱ\n"
            "ꜱᴍᴏᴏᴛʜ ᴇxᴘᴇʀɪᴇɴᴄᴇ"
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
    """Help — single unified message"""
    logger.info(f"HELP: User {m.from_user.id}")
    await _safe_reply(m, format_help(), parse_mode="HTML")


# ─── /mp3 ────────────────────────────────────────────────────────────────────

@dp.message(Command("mp3"))
async def cmd_mp3(m: Message):
    """Extract audio from replied video as 192k MP3"""
    logger.info(f"MP3: User {m.from_user.id}")

    # Must reply to a video
    reply = m.reply_to_message
    if not reply or not reply.video:
        await _safe_reply(m, "Reply to a video with /mp3", parse_mode="HTML")
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
                await _safe_reply(m, "⚠ Unable to extract audio.\n\nPlease try again.", parse_mode="HTML")
                return

            try:
                await progress.edit_text(_bar(90), parse_mode="HTML")
            except Exception:
                pass

            # Send audio
            safe_name = first_name[:32].replace("<", "").replace(">", "")
            caption = f'✓ Delivered — <a href="tg://user?id={user_id}">{safe_name}</a>'
            await bot.send_audio(
                m.chat.id,
                FSInputFile(audio_path),
                caption=caption,
                parse_mode="HTML",
            )

            # Delete progress
            try:
                await progress.delete()
            except Exception:
                pass

            logger.info(f"MP3: Sent to {user_id}")

    except Exception as e:
        logger.error(f"MP3 ERROR: {e}", exc_info=True)
        try:
            await progress.delete()
        except Exception:
            pass
        await _safe_reply(m, "⚠ Unable to extract audio.\n\nPlease try again.", parse_mode="HTML")


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
    await _safe_reply(m, format_stats(len(users), len(groups)), parse_mode="HTML")


@dp.message(Command("broadcast"))
async def cmd_broadcast(m: Message):
    """
    Broadcast to all users + groups. Admin only.

    Usage:
      /broadcast <text>          — broadcast text message
      /broadcast (reply to msg) — broadcast that exact message (any type)
    """
    if not _is_admin(m.from_user.id):
        await _safe_reply(m, "⛔ You are not authorized.", parse_mode="HTML")
        return

    # If replying to a message — broadcast that message (any media type)
    if m.reply_to_message:
        reply = m.reply_to_message
        logger.info(f"BROADCAST: Admin {m.from_user.id} broadcasting replied message")
        await _safe_reply(m, format_broadcast_started(), parse_mode="HTML")
        asyncio.create_task(
            run_broadcast(bot, m.from_user.id, reply_to_msg=reply)
        )
        return

    # Otherwise broadcast text from command
    parts = (m.text or "").split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await _safe_reply(
            m,
            "Usage:\n"
            "/broadcast Your message here\n\n"
            "Or reply to any message with /broadcast to broadcast it.",
            parse_mode="HTML",
        )
        return

    broadcast_text = parts[1].strip()
    logger.info(f"BROADCAST: Admin {m.from_user.id} starting text broadcast: {broadcast_text[:50]}")

    await _safe_reply(m, format_broadcast_started(), parse_mode="HTML")

    asyncio.create_task(
        run_broadcast(bot, m.from_user.id, text=broadcast_text)
    )


@dp.message(Command("broadcast_media"))
async def cmd_broadcast_media(m: Message):
    """Broadcast media (reply to media). Admin only. Legacy — use /broadcast instead."""
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
        reply.sticker,
    ])

    if not has_media and not reply.text:
        await _safe_reply(m, "Reply to a message with media or text.", parse_mode="HTML")
        return

    await _safe_reply(m, format_broadcast_started(), parse_mode="HTML")

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
        await _safe_reply(m, "⛔ You are not authorized.", parse_mode="HTML")
        return

    configured = await _get_configured_emoji_keys()
    keyboard = await _build_assign_keyboard(configured)
    menu_text = format_assign_menu(configured)

    # If any position is configured, show a sticker preview for the first one
    for key in EMOJI_POSITIONS.keys():
        if key in configured:
            file_id = await redis_client.get(f"{_EMOJI_KEY_PREFIX}{key}")
            if file_id:
                try:
                    await bot.send_sticker(m.chat.id, file_id)
                except Exception:
                    pass
            break

    await _safe_reply(m, menu_text, reply_markup=keyboard, parse_mode="HTML")


@dp.callback_query(lambda c: c.data and c.data.startswith("assign:"))
async def cb_assign(callback):
    """Handle emoji assignment button tap"""
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Unauthorized", show_alert=True)
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


@dp.message(lambda m: m.sticker and m.from_user and m.from_user.id in _assign_pending)
async def handle_assign_sticker(m: Message):
    """Receive sticker for emoji assignment"""
    if not _is_admin(m.from_user.id):
        return

    key = _assign_pending.pop(m.from_user.id, None)
    if not key or key not in EMOJI_POSITIONS:
        return

    file_id = m.sticker.file_id
    redis_key = f"{_EMOJI_KEY_PREFIX}{key}"
    await redis_client.set(redis_key, file_id)

    label = EMOJI_POSITIONS[key]
    logger.info(f"ASSIGN: Admin {m.from_user.id} set {key} = {file_id[:20]}...")

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
