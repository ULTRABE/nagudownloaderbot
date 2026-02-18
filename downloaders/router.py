"""Download router — Routes URLs to appropriate handlers, admin commands"""
import asyncio
import re
from aiogram import F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from pathlib import Path
from aiogram.types import FSInputFile

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
    premium_panel,
    format_user_id,
    styled_text,
    mention,
    quoted_block,
)
from utils.logger import logger
from utils.broadcast import (
    register_user,
    register_group,
    get_all_users,
    get_all_groups,
    run_broadcast,
)

# Link regex pattern
LINK_RE = re.compile(r"https?://\S+")

# ═══════════════════════════════════════════════════════════
# START COMMAND
# ═══════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def start_command(m: Message):
    """Start command with image and clickable user mention — registers user"""
    logger.info(f"START: User {m.from_user.id}")
    
    from utils.user_state import user_state_manager
    
    # Register user as started
    await user_state_manager.mark_user_started(m.from_user.id)
    await user_state_manager.mark_user_unblocked(m.from_user.id)
    
    # Register for broadcasts (private chats only)
    if m.chat.type == "private":
        await register_user(m.from_user.id)
    
    picture_path = Path("assets/picture.png")
    caption = format_welcome(m.from_user, m.from_user.id)
    
    if m.text and "start=spotify" in m.text:
        caption += f"\n\n✅ {styled_text('You are registered! You can now send Spotify playlist links in groups.')}"
    
    if picture_path.exists():
        try:
            await m.reply_photo(
                FSInputFile(picture_path),
                caption=caption,
                parse_mode="HTML"
            )
            return
        except Exception as e:
            logger.error(f"Failed to send start image: {e}")
    
    await m.reply(caption, parse_mode="HTML")

# ═══════════════════════════════════════════════════════════
# HELP COMMAND
# ═══════════════════════════════════════════════════════════

@dp.message(Command("help"))
async def help_command(m: Message):
    """Help command with styled sections"""
    logger.info(f"HELP: User {m.from_user.id}")
    
    await m.reply(format_help_video(), parse_mode="HTML")
    await asyncio.sleep(0.2)
    await m.reply(format_help_music(), parse_mode="HTML")
    await asyncio.sleep(0.2)
    await m.reply(format_help_info(), parse_mode="HTML")

# ═══════════════════════════════════════════════════════════
# INFO COMMANDS
# ═══════════════════════════════════════════════════════════

@dp.message(Command("id"))
async def cmd_id(m: Message):
    """Get user ID"""
    if m.reply_to_message:
        user = m.reply_to_message.from_user
        lines = [
            f"Name: {user.first_name}",
            f"Username: @{user.username}" if user.username else "Username: None",
            f"ID: {format_user_id(user.id)}"
        ]
        await m.reply(premium_panel("User ID Info", lines), parse_mode="HTML")
    else:
        lines = [
            f"Name: {m.from_user.first_name}",
            f"Username: @{m.from_user.username}" if m.from_user.username else "Username: None",
            f"ID: {format_user_id(m.from_user.id)}"
        ]
        await m.reply(premium_panel("Your ID Info", lines), parse_mode="HTML")

@dp.message(Command("chatid"))
async def cmd_chatid(m: Message):
    """Get chat ID"""
    chat_title = m.chat.title if m.chat.title else "Private Chat"
    lines = [
        f"Chat: {chat_title}",
        f"Type: {m.chat.type}",
        f"ID: {format_user_id(m.chat.id)}"
    ]
    await m.reply(premium_panel("Chat ID Info", lines), parse_mode="HTML")

@dp.message(Command("myinfo"))
async def cmd_myinfo(m: Message):
    """Get detailed user info"""
    user = m.from_user
    chat_title = m.chat.title if m.chat.title else "Private"
    
    lines = [
        f"{styled_text('User Details')}",
        f"  First Name: {user.first_name}",
        f"  Last Name: {user.last_name}" if user.last_name else "  Last Name: None",
        f"  Username: @{user.username}" if user.username else "  Username: None",
        f"  ID: {format_user_id(user.id)}",
        f"  Language: {user.language_code}" if user.language_code else "  Language: Unknown",
        "",
        f"{styled_text('Chat Details')}",
        f"  Chat: {chat_title}",
        f"  Type: {m.chat.type}",
        f"  ID: {format_user_id(m.chat.id)}"
    ]
    await m.reply(premium_panel("Your Information", lines), parse_mode="HTML")

# ═══════════════════════════════════════════════════════════
# ADMIN COMMANDS
# ═══════════════════════════════════════════════════════════

def _is_admin(user_id: int) -> bool:
    return config.is_admin(user_id)

@dp.message(Command("admin"))
async def cmd_admin(m: Message):
    """Admin panel — admin only"""
    if not _is_admin(m.from_user.id):
        return  # Silently ignore
    
    users = await get_all_users()
    groups = await get_all_groups()
    stats = {"users": len(users), "groups": len(groups)}
    
    await m.reply(format_admin_panel(stats), parse_mode="HTML")

@dp.message(Command("stats"))
async def cmd_stats(m: Message):
    """Bot stats — admin only"""
    if not _is_admin(m.from_user.id):
        return
    
    users = await get_all_users()
    groups = await get_all_groups()
    
    lines = [
        f"📊 {styled_text('Bot Statistics')}",
        "━" * 30,
        "",
        f"  👤 Registered users: {len(users)}",
        f"  👥 Registered groups: {len(groups)}",
    ]
    await m.reply(quoted_block("\n".join(lines)), parse_mode="HTML")

@dp.message(Command("broadcast"))
async def cmd_broadcast(m: Message):
    """
    Broadcast text message to all users and groups.
    Admin only. Usage: /broadcast <message>
    """
    if not _is_admin(m.from_user.id):
        return
    
    # Extract message text (everything after /broadcast)
    parts = m.text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await m.reply(
            "Usage: <code>/broadcast Your message here</code>",
            parse_mode="HTML"
        )
        return
    
    broadcast_text = parts[1].strip()
    
    users = await get_all_users()
    groups = await get_all_groups()
    total = len(users) + len(groups)
    
    confirm = await m.reply(
        f"📡 Starting broadcast to <b>{total}</b> recipients...",
        parse_mode="HTML"
    )
    
    # Run broadcast in background
    asyncio.create_task(
        run_broadcast(bot, m.from_user.id, text=broadcast_text)
    )

@dp.message(Command("broadcast_media"))
async def cmd_broadcast_media(m: Message):
    """
    Broadcast media message (reply to media).
    Admin only.
    """
    if not _is_admin(m.from_user.id):
        return
    
    if not m.reply_to_message:
        await m.reply("Reply to a media message to broadcast it.")
        return
    
    reply = m.reply_to_message
    
    # Verify it has media
    has_media = any([
        reply.photo, reply.video, reply.audio,
        reply.document, reply.animation, reply.voice
    ])
    
    if not has_media and not reply.text:
        await m.reply("Reply to a message with media or text to broadcast.")
        return
    
    users = await get_all_users()
    groups = await get_all_groups()
    total = len(users) + len(groups)
    
    await m.reply(
        f"📡 Starting media broadcast to <b>{total}</b> recipients...",
        parse_mode="HTML"
    )
    
    asyncio.create_task(
        run_broadcast(bot, m.from_user.id, reply_to_msg=reply)
    )

# ═══════════════════════════════════════════════════════════
# GROUP REGISTRATION
# ═══════════════════════════════════════════════════════════

@dp.message(F.new_chat_members)
async def on_bot_added_to_group(m: Message):
    """Register group when bot is added"""
    bot_me = await bot.get_me()
    for member in m.new_chat_members:
        if member.id == bot_me.id:
            await register_group(m.chat.id)
            logger.info(f"Registered group: {m.chat.id} ({m.chat.title})")
            break

# ═══════════════════════════════════════════════════════════
# LINK HANDLER
# ═══════════════════════════════════════════════════════════

@dp.message(F.text.regexp(LINK_RE))
async def handle_link(m: Message):
    """Route incoming links to appropriate downloader"""
    url = m.text.strip()
    
    logger.info(f"LINK: {url[:60]} from user {m.from_user.id}")
    
    # Register group if in group chat
    if m.chat.type in ("group", "supergroup"):
        await register_group(m.chat.id)
    
    # Delete user's link after 5 seconds (except Spotify)
    if "spotify.com" not in url.lower():
        async def delete_link_later():
            await asyncio.sleep(5)
            try:
                await m.delete()
            except Exception:
                pass
        asyncio.create_task(delete_link_later())
    
    try:
        if "instagram.com" in url.lower():
            await handle_instagram(m, url)
        elif "youtube.com" in url.lower() or "youtu.be" in url.lower() or "music.youtube.com" in url.lower():
            await handle_youtube(m, url)
        elif "pinterest.com" in url.lower() or "pin.it" in url.lower():
            await handle_pinterest(m, url)
        elif "spotify.com" in url.lower():
            await handle_spotify_playlist(m, url)
        else:
            await m.answer("Unsupported platform.")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error handling link: {e}")
        await m.answer("Could not process this link.")

def register_download_handlers():
    """Register download handlers — called from main"""
    logger.info("Download handlers registered")
