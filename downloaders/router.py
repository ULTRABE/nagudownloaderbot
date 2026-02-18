"""
Download router — Routes URLs to handlers, admin commands.

Design:
  - All media replies quote the original message (reply_to_message_id)
  - Progress messages deleted after send
  - Caption: ✓ Delivered (minimal)
  - Group registration on bot join
  - Broadcast: admin-only, background, with pin
"""
import asyncio
import re
from pathlib import Path

from aiogram import F
from aiogram.types import Message, FSInputFile
from aiogram.filters import CommandStart, Command

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
    code_panel,
    mono,
    mention,
    format_user_id,
)
from utils.logger import logger
from utils.broadcast import (
    register_user,
    register_group,
    get_all_users,
    get_all_groups,
    run_broadcast,
)

# Link regex
LINK_RE = re.compile(r"https?://\S+")

# ─── /start ───────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def start_command(m: Message):
    """Start command — register user, show welcome panel"""
    logger.info(f"START: User {m.from_user.id}")

    from utils.user_state import user_state_manager
    await user_state_manager.mark_user_started(m.from_user.id)
    await user_state_manager.mark_user_unblocked(m.from_user.id)

    if m.chat.type == "private":
        await register_user(m.from_user.id)

    picture_path = Path("assets/picture.png")
    caption = format_welcome(m.from_user, m.from_user.id)

    if picture_path.exists():
        try:
            await m.reply_photo(
                FSInputFile(picture_path),
                caption=caption,
                parse_mode="HTML",
            )
            return
        except Exception as e:
            logger.error(f"Failed to send start image: {e}")

    await m.reply(caption, parse_mode="HTML")

# ─── /help ────────────────────────────────────────────────────────────────────

@dp.message(Command("help"))
async def help_command(m: Message):
    """Help — three panels"""
    logger.info(f"HELP: User {m.from_user.id}")
    await m.reply(format_help_video(), parse_mode="HTML")
    await asyncio.sleep(0.15)
    await m.reply(format_help_music(), parse_mode="HTML")
    await asyncio.sleep(0.15)
    await m.reply(format_help_info(), parse_mode="HTML")

# ─── Info commands ────────────────────────────────────────────────────────────

@dp.message(Command("id"))
async def cmd_id(m: Message):
    if m.reply_to_message:
        user = m.reply_to_message.from_user
        lines = [
            "  USER  ID",
            "---",
            f"  Name  ·  {(user.first_name or '')[:20]}",
            f"  User  ·  @{user.username}" if user.username else "  User  ·  —",
            f"  ID    ·  {user.id}",
        ]
    else:
        user = m.from_user
        lines = [
            "  YOUR  ID",
            "---",
            f"  Name  ·  {(user.first_name or '')[:20]}",
            f"  User  ·  @{user.username}" if user.username else "  User  ·  —",
            f"  ID    ·  {user.id}",
        ]
    await m.reply(code_panel(lines, width=32), parse_mode="HTML")

@dp.message(Command("chatid"))
async def cmd_chatid(m: Message):
    chat_title = (m.chat.title or "Private Chat")[:20]
    lines = [
        "  CHAT  ID",
        "---",
        f"  Chat  ·  {chat_title}",
        f"  Type  ·  {m.chat.type}",
        f"  ID    ·  {m.chat.id}",
    ]
    await m.reply(code_panel(lines, width=32), parse_mode="HTML")

@dp.message(Command("myinfo"))
async def cmd_myinfo(m: Message):
    user = m.from_user
    chat_title = (m.chat.title or "Private")[:20]
    lines = [
        "  MY  INFO",
        "---",
        f"  Name  ·  {(user.first_name or '')[:20]}",
        f"  Last  ·  {(user.last_name or '—')[:20]}",
        f"  User  ·  @{user.username}" if user.username else "  User  ·  —",
        f"  ID    ·  {user.id}",
        f"  Lang  ·  {user.language_code or '—'}",
        "---",
        f"  Chat  ·  {chat_title}",
        f"  Type  ·  {m.chat.type}",
        f"  CID   ·  {m.chat.id}",
    ]
    await m.reply(code_panel(lines, width=32), parse_mode="HTML")

# ─── Admin commands ───────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return config.is_admin(user_id)

@dp.message(Command("admin"))
async def cmd_admin(m: Message):
    if not _is_admin(m.from_user.id):
        return
    users  = await get_all_users()
    groups = await get_all_groups()
    stats  = {"users": len(users), "groups": len(groups)}
    await m.reply(format_admin_panel(stats), parse_mode="HTML")

@dp.message(Command("stats"))
async def cmd_stats(m: Message):
    if not _is_admin(m.from_user.id):
        return
    users  = await get_all_users()
    groups = await get_all_groups()
    lines = [
        "  BOT  STATS",
        "---",
        f"  Users   ·  {len(users)}",
        f"  Groups  ·  {len(groups)}",
    ]
    await m.reply(code_panel(lines, width=32), parse_mode="HTML")

@dp.message(Command("broadcast"))
async def cmd_broadcast(m: Message):
    """Broadcast text to all users + groups. Admin only."""
    if not _is_admin(m.from_user.id):
        return

    parts = m.text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await m.reply(
            mono("  Usage: /broadcast Your message here"),
            parse_mode="HTML",
        )
        return

    broadcast_text = parts[1].strip()
    users  = await get_all_users()
    groups = await get_all_groups()
    total  = len(users) + len(groups)

    await m.reply(
        mono(f"  ⬆  Broadcasting to {total} recipients..."),
        parse_mode="HTML",
    )

    asyncio.create_task(
        run_broadcast(bot, m.from_user.id, text=broadcast_text)
    )

@dp.message(Command("broadcast_media"))
async def cmd_broadcast_media(m: Message):
    """Broadcast media (reply to media). Admin only."""
    if not _is_admin(m.from_user.id):
        return

    if not m.reply_to_message:
        await m.reply(mono("  Reply to a media message to broadcast it."))
        return

    reply = m.reply_to_message
    has_media = any([
        reply.photo, reply.video, reply.audio,
        reply.document, reply.animation, reply.voice,
    ])

    if not has_media and not reply.text:
        await m.reply(mono("  Reply to a message with media or text."))
        return

    users  = await get_all_users()
    groups = await get_all_groups()
    total  = len(users) + len(groups)

    await m.reply(
        mono(f"  ⬆  Broadcasting media to {total} recipients..."),
        parse_mode="HTML",
    )

    asyncio.create_task(
        run_broadcast(bot, m.from_user.id, reply_to_msg=reply)
    )

# ─── Group registration ───────────────────────────────────────────────────────

@dp.message(F.new_chat_members)
async def on_bot_added_to_group(m: Message):
    """Register group when bot is added"""
    bot_me = await bot.get_me()
    for member in m.new_chat_members:
        if member.id == bot_me.id:
            await register_group(m.chat.id)
            logger.info(f"Registered group: {m.chat.id} ({m.chat.title})")
            break

# ─── Link handler ─────────────────────────────────────────────────────────────

@dp.message(F.text.regexp(LINK_RE))
async def handle_link(m: Message):
    """Route incoming links to appropriate downloader"""
    url = m.text.strip()
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
            await m.reply(mono("  ✗  Unsupported platform"))
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error handling link: {e}")
        try:
            await m.reply(mono("  ✗  Could not process this link"))
        except Exception:
            pass


def register_download_handlers():
    """Register download handlers — called from main"""
    logger.info("Download handlers registered")
