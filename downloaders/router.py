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

# Absolute path to assets directory — works regardless of CWD at runtime
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

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
    build_start_keyboard,
    build_back_keyboard,
    build_manage_keyboard,
    build_manage_back_keyboard,
    format_help,
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
    mono,
    safe_caption,
    build_safe_media_caption,
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
from utils.proxy_manager import proxy_manager

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

async def _safe_reply(m: Message, text: str, **kwargs):
    """Reply with fallback to plain send if original message was deleted.
    Returns the sent Message object, or None on total failure."""
    try:
        return await m.reply(text, **kwargs)
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "replied message not found" in err_str:
            try:
                return await bot.send_message(m.chat.id, text, **kwargs)
            except Exception:
                return None
        else:
            logger.error(f"Reply failed: {e}")
            return None

# ─── /start ───────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def start_command(m: Message):
    """
    Start command — register user, show branded welcome UI.

    UI structure:
      Header → Tagline → Platforms → Instruction
      Inline keyboard: Download | Status | Help | Settings |
                       Updates | Support | Owner | Add Me To Group

    All values dynamic — no hardcoded links or usernames.
    Keyboard built via centralized build_start_keyboard().
    """
    logger.info(f"START: User {m.from_user.id}")

    from utils.user_state import user_state_manager

    await user_state_manager.mark_user_started(m.from_user.id)
    await user_state_manager.mark_user_unblocked(m.from_user.id)

    if m.chat.type == "private":
        await register_user(m.from_user.id)

    # Fetch bot username dynamically — never hardcoded
    try:
        bot_me = await bot.get_me()
        bot_username = bot_me.username or ""
    except Exception:
        bot_username = ""

    welcome_text = await format_welcome(m.from_user, m.from_user.id)
    keyboard = await build_start_keyboard(bot_username)

    picture_path = _ASSETS_DIR / "picture.png"
    if picture_path.exists():
        try:
            await m.reply_photo(
                FSInputFile(picture_path),
                caption=welcome_text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            return
        except Exception as e:
            logger.error(f"Failed to send start image: {e}")

    await _safe_reply(m, welcome_text, parse_mode="HTML", reply_markup=keyboard)


# ─── Inline button callbacks (start keyboard) ─────────────────────────────────

async def _edit_inline(callback, text: str, keyboard=None):
    """Edit the message in-place — works for both photo captions and text messages."""
    kb = keyboard or build_back_keyboard()
    try:
        # Try edit caption first (for photo messages from /start)
        await callback.message.edit_caption(
            caption=text,
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception:
        try:
            # Fallback: edit text (for plain text messages)
            await callback.message.edit_text(
                text=text,
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "cb_download")
async def cb_download(callback):
    """Download — edit in-place, no new message"""
    await callback.answer()
    _dl = await get_emoji_async("DOWNLOAD")
    yt = await get_emoji_async("YT")
    sp = await get_emoji_async("SPOTIFY")
    ig = await get_emoji_async("INSTA")
    pin = await get_emoji_async("PINTEREST")
    text = (
        f"{_dl} <b>How to Download</b>\n\n"
        "Paste any supported link in the chat.\n\n"
        f"  {yt}  YouTube\n"
        f"  {ig}  Instagram\n"
        f"  {sp}  Spotify\n"
        f"  {pin}  Pinterest"
    )
    await _edit_inline(callback, text)


@dp.callback_query(lambda c: c.data == "cb_help")
async def cb_help(callback):
    """Help — edit in-place"""
    await callback.answer()
    info = await get_emoji_async("INFO")
    text = (
        f"{info} <b>Commands</b>\n\n"
        "/start  ·  Start the bot\n"
        "/help  ·  Show help\n"
        "/id  ·  Get user ID\n"
        "/myinfo  ·  Account info\n"
        "/mp3  ·  Extract audio\n"
        "/ping  ·  Latency check\n\n"
        "👮 <b>Group Admin</b>\n\n"
        "/ban · /kick · /mute · /unmute\n"
        "/pin · /unpin · /purge"
    )
    await _edit_inline(callback, text)


@dp.callback_query(lambda c: c.data == "cb_settings")
async def cb_settings(callback):
    """Settings — edit in-place"""
    await callback.answer()
    _info = await get_emoji_async("INFO")
    text = (
        f"{_info} <b>Settings</b>\n\n"
        "/assign  ·  Configure emojis\n"
        "/status  ·  Bot status\n"
        "/myinfo  ·  Your account info"
    )
    await _edit_inline(callback, text)


@dp.callback_query(lambda c: c.data == "cb_back")
async def cb_back(callback):
    """Back button — restore main menu"""
    await callback.answer()
    try:
        bot_me = await bot.get_me()
        bot_username = bot_me.username or ""
    except Exception:
        bot_username = ""
    welcome_text = await format_welcome(callback.from_user, callback.from_user.id)
    keyboard = await build_start_keyboard(bot_username)
    await _edit_inline(callback, welcome_text, keyboard)


# ─── Manage Group inline menus ────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data == "cb_manage")
async def cb_manage(callback):
    """Manage Group — main submenu"""
    await callback.answer()
    text = (
        "👮 <b>Group Management</b>\n\n"
        "Select a category to see available commands.\n"
        "All commands require admin permissions."
    )
    await _edit_inline(callback, text, build_manage_keyboard())


@dp.callback_query(lambda c: c.data == "mg_mod")
async def cb_mg_mod(callback):
    """Moderation submenu"""
    await callback.answer()
    text = (
        "🛡 <b>Moderation</b>\n\n"
        "/ban  ·  Ban user (reply)\n"
        "/unban  ·  Unban user\n"
        "/mute  ·  Mute user (reply)\n"
        "/unmute  ·  Unmute user (reply)\n"
        "/kick  ·  Kick user (reply)"
    )
    await _edit_inline(callback, text, build_manage_back_keyboard())


@dp.callback_query(lambda c: c.data == "mg_pins")
async def cb_mg_pins(callback):
    """Pins submenu"""
    await callback.answer()
    text = (
        "📌 <b>Pinned Messages</b>\n\n"
        "/pin  ·  Pin message (reply)\n"
        "/unpin  ·  Unpin message\n"
        "/pinned  ·  Show current pin"
    )
    await _edit_inline(callback, text, build_manage_back_keyboard())


@dp.callback_query(lambda c: c.data == "mg_warn")
async def cb_mg_warn(callback):
    """Warnings submenu"""
    await callback.answer()
    text = (
        "⚠ <b>Warning System</b>\n\n"
        "/warn  ·  Warn a user (reply)\n"
        "/unwarn  ·  Remove a warn (reply)\n"
        "/warns  ·  Check user warns (reply)\n\n"
        "⚡ 3 warnings = auto-mute"
    )
    await _edit_inline(callback, text, build_manage_back_keyboard())


@dp.callback_query(lambda c: c.data == "mg_clean")
async def cb_mg_clean(callback):
    """Cleanup submenu"""
    await callback.answer()
    text = (
        "🧹 <b>Cleanup</b>\n\n"
        "/purge N  ·  Delete last N messages\n"
        "/del  ·  Delete replied message"
    )
    await _edit_inline(callback, text, build_manage_back_keyboard())


@dp.callback_query(lambda c: c.data == "mg_info")
async def cb_mg_info(callback):
    """Group Info submenu"""
    await callback.answer()
    text = (
        "📊 <b>Group Info</b>\n\n"
        "/chatid  ·  Get chat ID\n"
        "/staff  ·  List all admins"
    )
    await _edit_inline(callback, text, build_manage_back_keyboard())


@dp.callback_query(lambda c: c.data == "mg_members")
async def cb_mg_members(callback):
    """Members submenu"""
    await callback.answer()
    text = (
        "👥 <b>Members</b>\n\n"
        "/info  ·  User info (reply)\n"
        "/id  ·  Get user ID (reply)"
    )
    await _edit_inline(callback, text, build_manage_back_keyboard())


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
    """Status — edit in-place"""
    uptime_secs = int(time.time() - _BOT_START_TIME)
    days = uptime_secs // 86400
    hours = (uptime_secs % 86400) // 3600
    uptime_str = f"{days}d {hours}h"
    await callback.answer()
    text = await format_status(active_jobs=0, queue=0, uptime=uptime_str)
    await _edit_inline(callback, text)


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


# ─── Proxy management commands ─────────────────────────────────────────────────

@dp.message(Command("addpxy"))
async def cmd_addpxy(m: Message):
    """
    Add proxies to the pool. Admin only.
    Usage: /addpxy ip:port ip:port ...
    Accepts space, newline, or comma separated proxies.
    Validates each one before adding.
    """
    if not _is_admin(m.from_user.id):
        _err = await get_emoji_async("ERROR")
        await _safe_reply(m, f"{_err} 𝐀ᴅᴍɪɴ 𝐎ɴʟʏ", parse_mode="HTML")
        return

    # Parse proxies from message text
    parts = (m.text or "").split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        _info = await get_emoji_async("INFO")
        await _safe_reply(
            m,
            f"{_info} <b>Add Proxies</b>\n\n"
            f"/addpxy ip:port ip:port ...\n\n"
            f"Separate with spaces, commas, or newlines.",
            parse_mode="HTML",
        )
        return

    raw_text = parts[1].strip()
    # Split by comma, newline, or space
    import re as _re
    raw_list = _re.split(r"[,\s]+", raw_text)
    raw_list = [p.strip() for p in raw_list if p.strip()]

    if not raw_list:
        _err = await get_emoji_async("ERROR")
        await _safe_reply(m, f"{_err} No valid proxies found in message.", parse_mode="HTML")
        return

    _proc = await get_emoji_async("PROCESS")
    status = await _safe_reply(m, f"{_proc} Validating {len(raw_list)} proxies...", parse_mode="HTML")

    added, failed = await proxy_manager.add_proxies(raw_list)
    stats = proxy_manager.get_stats()

    _success = await get_emoji_async("SUCCESS")
    result_text = (
        f"{_success} <b>Proxies Added</b>\n\n"
        f"✅ Added: {added}\n"
        f"❌ Failed: {failed}\n\n"
        f"Pool: {stats['live']} live / {stats['total']} total"
    )
    try:
        if status:
            await status.edit_text(result_text, parse_mode="HTML")
        else:
            await _safe_reply(m, result_text, parse_mode="HTML")
    except Exception:
        await _safe_reply(m, result_text, parse_mode="HTML")


@dp.message(Command("rm"))
async def cmd_rm(m: Message):
    """
    Remove a proxy from the pool. Admin only.
    Usage: /rm ip:port
    """
    if not _is_admin(m.from_user.id):
        _err = await get_emoji_async("ERROR")
        await _safe_reply(m, f"{_err} 𝐀ᴅᴍɪɴ 𝐎ɴʟʏ", parse_mode="HTML")
        return

    parts = (m.text or "").split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        _info = await get_emoji_async("INFO")
        await _safe_reply(
            m,
            f"{_info} <b>Remove Proxy</b>\n\n/rm ip:port",
            parse_mode="HTML",
        )
        return

    proxy_str = parts[1].strip()
    ok = await proxy_manager.remove_proxy(proxy_str)
    stats = proxy_manager.get_stats()

    if ok:
        _success = await get_emoji_async("SUCCESS")
        await _safe_reply(
            m,
            f"{_success} Proxy removed.\n\nPool: {stats['live']} live / {stats['total']} total",
            parse_mode="HTML",
        )
    else:
        _err = await get_emoji_async("ERROR")
        await _safe_reply(m, f"{_err} Proxy not found in pool.", parse_mode="HTML")


@dp.message(Command("clean"))
async def cmd_clean(m: Message):
    """
    Scan all proxies and remove dead ones. Admin only.
    Usage: /clean
    """
    if not _is_admin(m.from_user.id):
        _err = await get_emoji_async("ERROR")
        await _safe_reply(m, f"{_err} 𝐀ᴅᴍɪɴ 𝐎ɴʟʏ", parse_mode="HTML")
        return

    stats_before = proxy_manager.get_stats()
    _proc = await get_emoji_async("PROCESS")
    status = await _safe_reply(
        m,
        f"{_proc} Scanning {stats_before['total']} proxies... This may take a minute.",
        parse_mode="HTML",
    )

    alive, removed = await proxy_manager.clean()
    stats = proxy_manager.get_stats()

    _success = await get_emoji_async("SUCCESS")
    result_text = (
        f"{_success} <b>Proxy Cleanup Done</b>\n\n"
        f"✅ Alive: {alive}\n"
        f"🗑 Removed: {removed}\n\n"
        f"Pool: {stats['live']} live"
    )
    try:
        if status:
            await status.edit_text(result_text, parse_mode="HTML")
        else:
            await _safe_reply(m, result_text, parse_mode="HTML")
    except Exception:
        await _safe_reply(m, result_text, parse_mode="HTML")


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

    # Skip messages that look like URLs — let link handlers process them
    _text = (m.text or "").strip()
    if _text.startswith("http://") or _text.startswith("https://"):
        # Cancel pending assignment so admin can restart via /assign later
        _assign_pending.pop(m.from_user.id, None)
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


# ─── Group management commands ─────────────────────────────────────────────────

async def _is_group_admin(m: Message) -> bool:
    """Check if the user is an admin in the current group chat."""
    if m.chat.type not in ("group", "supergroup"):
        return False
    try:
        member = await bot.get_chat_member(m.chat.id, m.from_user.id)
        return member.status in ("creator", "administrator")
    except Exception:
        return False


@dp.message(Command("ban"))
async def cmd_ban(m: Message):
    """Ban a user — reply to their message. Group admin only."""
    if not await _is_group_admin(m):
        return
    if not m.reply_to_message or not m.reply_to_message.from_user:
        await _safe_reply(m, "⚠ Reply to a user's message to ban them.", parse_mode="HTML")
        return
    target = m.reply_to_message.from_user
    try:
        await bot.ban_chat_member(m.chat.id, target.id)
        safe_name = _html_escape((target.first_name or "User")[:32])
        await _safe_reply(m, f"🚫 \"<a href=\"tg://user?id={target.id}\">{safe_name}</a>\" has been banned.", parse_mode="HTML")
    except Exception as e:
        await _safe_reply(m, f"⚠ Failed to ban: {_html_escape(str(e)[:60])}", parse_mode="HTML")


@dp.message(Command("unban"))
async def cmd_unban(m: Message):
    """Unban a user — reply or provide user ID. Group admin only."""
    if not await _is_group_admin(m):
        return
    # Try reply first
    if m.reply_to_message and m.reply_to_message.from_user:
        target_id = m.reply_to_message.from_user.id
    else:
        parts = (m.text or "").split()
        if len(parts) < 2 or not parts[1].strip().isdigit():
            await _safe_reply(m, "⚠ Reply to a user or use: /unban &lt;user_id&gt;", parse_mode="HTML")
            return
        target_id = int(parts[1].strip())
    try:
        await bot.unban_chat_member(m.chat.id, target_id, only_if_banned=True)
        await _safe_reply(m, f"✅ User <code>{target_id}</code> has been unbanned.", parse_mode="HTML")
    except Exception as e:
        await _safe_reply(m, f"⚠ Failed to unban: {_html_escape(str(e)[:60])}", parse_mode="HTML")


@dp.message(Command("mute"))
async def cmd_mute(m: Message):
    """Mute a user — reply to their message. Group admin only."""
    if not await _is_group_admin(m):
        return
    if not m.reply_to_message or not m.reply_to_message.from_user:
        await _safe_reply(m, "⚠ Reply to a user's message to mute them.", parse_mode="HTML")
        return
    target = m.reply_to_message.from_user
    try:
        from aiogram.types import ChatPermissions
        await bot.restrict_chat_member(m.chat.id, target.id, permissions=ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_other_messages=False,
        ))
        safe_name = _html_escape((target.first_name or "User")[:32])
        await _safe_reply(m, f"🔇 \"<a href=\"tg://user?id={target.id}\">{safe_name}</a>\" has been muted.", parse_mode="HTML")
    except Exception as e:
        await _safe_reply(m, f"⚠ Failed to mute: {_html_escape(str(e)[:60])}", parse_mode="HTML")


@dp.message(Command("unmute"))
async def cmd_unmute(m: Message):
    """Unmute a user — reply to their message. Group admin only."""
    if not await _is_group_admin(m):
        return
    if not m.reply_to_message or not m.reply_to_message.from_user:
        await _safe_reply(m, "⚠ Reply to a user's message to unmute them.", parse_mode="HTML")
        return
    target = m.reply_to_message.from_user
    try:
        from aiogram.types import ChatPermissions
        await bot.restrict_chat_member(m.chat.id, target.id, permissions=ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
        ))
        safe_name = _html_escape((target.first_name or "User")[:32])
        await _safe_reply(m, f"🔊 \"<a href=\"tg://user?id={target.id}\">{safe_name}</a>\" has been unmuted.", parse_mode="HTML")
    except Exception as e:
        await _safe_reply(m, f"⚠ Failed to unmute: {_html_escape(str(e)[:60])}", parse_mode="HTML")


@dp.message(Command("kick"))
async def cmd_kick(m: Message):
    """Kick (remove) a user — reply to their message. Group admin only."""
    if not await _is_group_admin(m):
        return
    if not m.reply_to_message or not m.reply_to_message.from_user:
        await _safe_reply(m, "⚠ Reply to a user's message to kick them.", parse_mode="HTML")
        return
    target = m.reply_to_message.from_user
    try:
        # Ban then unban = kick (remove without permanent ban)
        await bot.ban_chat_member(m.chat.id, target.id)
        await bot.unban_chat_member(m.chat.id, target.id, only_if_banned=True)
        safe_name = _html_escape((target.first_name or "User")[:32])
        await _safe_reply(m, f"👢 \"<a href=\"tg://user?id={target.id}\">{safe_name}</a>\" has been kicked.", parse_mode="HTML")
    except Exception as e:
        await _safe_reply(m, f"⚠ Failed to kick: {_html_escape(str(e)[:60])}", parse_mode="HTML")


@dp.message(Command("pin"))
async def cmd_pin(m: Message):
    """Pin a message — reply to the message to pin. Group admin only."""
    if not await _is_group_admin(m):
        return
    if not m.reply_to_message:
        await _safe_reply(m, "⚠ Reply to a message to pin it.", parse_mode="HTML")
        return
    try:
        await bot.pin_chat_message(m.chat.id, m.reply_to_message.message_id, disable_notification=False)
        await _safe_reply(m, "📌 Message pinned.", parse_mode="HTML")
    except Exception as e:
        await _safe_reply(m, f"⚠ Failed to pin: {_html_escape(str(e)[:60])}", parse_mode="HTML")


@dp.message(Command("unpin"))
async def cmd_unpin(m: Message):
    """Unpin the replied message or latest pin. Group admin only."""
    if not await _is_group_admin(m):
        return
    try:
        if m.reply_to_message:
            await bot.unpin_chat_message(m.chat.id, m.reply_to_message.message_id)
        else:
            await bot.unpin_chat_message(m.chat.id)
        await _safe_reply(m, "📌 Message unpinned.", parse_mode="HTML")
    except Exception as e:
        await _safe_reply(m, f"⚠ Failed to unpin: {_html_escape(str(e)[:60])}", parse_mode="HTML")


@dp.message(Command("purge"))
async def cmd_purge(m: Message):
    """Delete last N messages. Usage: /purge 10. Group admin only. Max 100."""
    if not await _is_group_admin(m):
        return
    parts = (m.text or "").split()
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await _safe_reply(m, "⚠ Usage: /purge &lt;number&gt; (max 100)", parse_mode="HTML")
        return
    count = min(int(parts[1].strip()), 100)
    if count < 1:
        return
    try:
        # Get message IDs to delete (current message + N before it)
        msg_ids = [m.message_id]
        # We can only delete messages by ID — collect from reply chain or estimate
        for i in range(1, count + 1):
            msg_ids.append(m.message_id - i)
        # Delete in batches (Telegram allows deleting multiple at once)
        for i in range(0, len(msg_ids), 100):
            batch = msg_ids[i:i+100]
            try:
                await bot.delete_messages(m.chat.id, batch)
            except Exception:
                # Fallback: delete one by one
                for mid in batch:
                    try:
                        await bot.delete_message(m.chat.id, mid)
                    except Exception:
                        pass
        logger.info(f"PURGE: {m.from_user.id} purged {count} messages in {m.chat.id}")
    except Exception as e:
        await _safe_reply(m, f"⚠ Purge failed: {_html_escape(str(e)[:60])}", parse_mode="HTML")


@dp.message(Command("del"))
async def cmd_del(m: Message):
    """Delete the replied message. Group admin only."""
    if not await _is_group_admin(m):
        return
    if not m.reply_to_message:
        await _safe_reply(m, "⚠ Reply to a message to delete it.", parse_mode="HTML")
        return
    try:
        await bot.delete_message(m.chat.id, m.reply_to_message.message_id)
        # Also delete the /del command message
        try:
            await m.delete()
        except Exception:
            pass
    except Exception as e:
        await _safe_reply(m, f"⚠ Failed to delete: {_html_escape(str(e)[:60])}", parse_mode="HTML")


@dp.message(Command("staff"))
async def cmd_staff(m: Message):
    """List all admins in the group."""
    if m.chat.type not in ("group", "supergroup"):
        await _safe_reply(m, "⚠ This command works in groups only.", parse_mode="HTML")
        return
    try:
        admins = await bot.get_chat_administrators(m.chat.id)
        lines = ["👮 <b>Group Staff</b>\n"]
        for admin in admins:
            user = admin.user
            safe_name = _html_escape((user.first_name or "User")[:32])
            role = "👑 Owner" if admin.status == "creator" else "🛡 Admin"
            mention = f'<a href="tg://user?id={user.id}">{safe_name}</a>'
            lines.append(f"  {role}  ·  {mention}")
        await _safe_reply(m, "\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await _safe_reply(m, f"⚠ Failed to get staff: {_html_escape(str(e)[:60])}", parse_mode="HTML")


@dp.message(Command("info"))
async def cmd_info(m: Message):
    """Show info about a user. Reply to their message."""
    if not m.reply_to_message or not m.reply_to_message.from_user:
        await _safe_reply(m, "⚠ Reply to a user's message.", parse_mode="HTML")
        return
    user = m.reply_to_message.from_user
    safe_name = _html_escape((user.first_name or "User")[:32])
    last = _html_escape((user.last_name or "")[:32])
    username = f"@{_html_escape(user.username)}" if user.username else "not set"
    mention = f'<a href="tg://user?id={user.id}">{safe_name}</a>'
    text = (
        f"👤 <b>User Info</b>\n\n"
        f"Name  ·  {mention}\n"
        f"Last  ·  {last or 'not set'}\n"
        f"Username  ·  {username}\n"
        f"ID  ·  <code>{user.id}</code>\n"
        f"Bot  ·  {'Yes' if user.is_bot else 'No'}\n"
        f"Premium  ·  {'Yes' if getattr(user, 'is_premium', False) else 'No'}"
    )
    await _safe_reply(m, text, parse_mode="HTML")


@dp.message(Command("pinned"))
async def cmd_pinned(m: Message):
    """Show the current pinned message."""
    if m.chat.type not in ("group", "supergroup"):
        await _safe_reply(m, "⚠ This command works in groups only.", parse_mode="HTML")
        return
    try:
        chat = await bot.get_chat(m.chat.id)
        pinned = chat.pinned_message
        if not pinned:
            await _safe_reply(m, "📌 No pinned message in this chat.", parse_mode="HTML")
            return
        # Link to the pinned message
        if chat.username:
            link = f"https://t.me/{chat.username}/{pinned.message_id}"
            await _safe_reply(m, f'📌 <a href="{link}">Pinned Message</a>', parse_mode="HTML")
        else:
            text_preview = (pinned.text or pinned.caption or "Media")[:100]
            safe_preview = _html_escape(text_preview)
            await _safe_reply(m, f"📌 <b>Pinned:</b> {safe_preview}", parse_mode="HTML")
    except Exception as e:
        await _safe_reply(m, f"⚠ Failed: {_html_escape(str(e)[:60])}", parse_mode="HTML")


# ─── Warning system (Redis-backed) ────────────────────────────────────────────

_WARN_MAX = 3  # 3 warnings = auto-mute


def _warn_key(chat_id: int, user_id: int) -> str:
    return f"warn:{chat_id}:{user_id}"


@dp.message(Command("warn"))
async def cmd_warn(m: Message):
    """Warn a user. 3 warnings = auto-mute. Group admin only."""
    if not await _is_group_admin(m):
        return
    if not m.reply_to_message or not m.reply_to_message.from_user:
        await _safe_reply(m, "⚠ Reply to a user's message to warn them.", parse_mode="HTML")
        return
    target = m.reply_to_message.from_user
    key = _warn_key(m.chat.id, target.id)

    # Increment warn count in Redis
    count = await redis_client.incr(key)
    # Set expiry (30 days)
    await redis_client.expire(key, 86400 * 30)

    safe_name = _html_escape((target.first_name or "User")[:32])
    mention = f'"<a href="tg://user?id={target.id}">{safe_name}</a>"'

    if count >= _WARN_MAX:
        # Auto-mute on 3 warnings
        try:
            from aiogram.types import ChatPermissions
            await bot.restrict_chat_member(m.chat.id, target.id, permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
            ))
            await redis_client.delete(key)  # Reset warns after mute
            await _safe_reply(
                m,
                f"⚠ {mention} warned ({count}/{_WARN_MAX})\n\n"
                f"🔇 <b>Auto-muted</b> — reached {_WARN_MAX} warnings.",
                parse_mode="HTML",
            )
        except Exception as e:
            await _safe_reply(m, f"⚠ Warned but failed to mute: {_html_escape(str(e)[:60])}", parse_mode="HTML")
    else:
        await _safe_reply(
            m,
            f"⚠ {mention} warned ({count}/{_WARN_MAX})",
            parse_mode="HTML",
        )


@dp.message(Command("unwarn"))
async def cmd_unwarn(m: Message):
    """Remove a warning from a user. Group admin only."""
    if not await _is_group_admin(m):
        return
    if not m.reply_to_message or not m.reply_to_message.from_user:
        await _safe_reply(m, "⚠ Reply to a user's message.", parse_mode="HTML")
        return
    target = m.reply_to_message.from_user
    key = _warn_key(m.chat.id, target.id)

    current = await redis_client.get(key)
    count = int(current) if current else 0

    if count <= 0:
        safe_name = _html_escape((target.first_name or "User")[:32])
        await _safe_reply(m, f"✅ {safe_name} has no warnings.", parse_mode="HTML")
        return

    new_count = count - 1
    if new_count <= 0:
        await redis_client.delete(key)
    else:
        await redis_client.set(key, str(new_count))
        await redis_client.expire(key, 86400 * 30)

    safe_name = _html_escape((target.first_name or "User")[:32])
    mention = f'"<a href="tg://user?id={target.id}">{safe_name}</a>"'
    await _safe_reply(m, f"✅ {mention} warning removed ({new_count}/{_WARN_MAX})", parse_mode="HTML")


@dp.message(Command("warns"))
async def cmd_warns(m: Message):
    """Check how many warnings a user has. Group admin only."""
    if not await _is_group_admin(m):
        return
    if not m.reply_to_message or not m.reply_to_message.from_user:
        await _safe_reply(m, "⚠ Reply to a user's message.", parse_mode="HTML")
        return
    target = m.reply_to_message.from_user
    key = _warn_key(m.chat.id, target.id)

    current = await redis_client.get(key)
    count = int(current) if current else 0

    safe_name = _html_escape((target.first_name or "User")[:32])
    mention = f'"<a href="tg://user?id={target.id}">{safe_name}</a>"'
    await _safe_reply(m, f"⚠ {mention} has {count}/{_WARN_MAX} warnings", parse_mode="HTML")


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

    # Detect supported platform
    is_instagram = "instagram.com" in url_lower
    is_youtube = "youtube.com" in url_lower or "youtu.be" in url_lower
    is_pinterest = "pinterest.com" in url_lower or "pin.it" in url_lower
    is_spotify = "spotify.com" in url_lower or url_lower.startswith("spotify:")
    is_supported = is_instagram or is_youtube or is_pinterest or is_spotify

    # Delete link message IMMEDIATELY for supported platforms only
    if is_supported:
        try:
            await m.delete()
        except Exception:
            pass

    try:
        if is_instagram:
            await handle_instagram(m, url)
        elif is_youtube:
            await handle_youtube(m, url)
        elif is_pinterest:
            await handle_pinterest(m, url)
        elif is_spotify:
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
