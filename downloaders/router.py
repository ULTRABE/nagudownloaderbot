"""Download router - Routes URLs to appropriate handlers"""
import asyncio
import re
from aiogram import F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command

from core.bot import dp, bot
from downloaders.instagram import handle_instagram
from downloaders.pinterest import handle_pinterest
from downloaders.youtube import handle_youtube
from downloaders.spotify import handle_spotify_playlist
from ui.formatting import (
    format_welcome,
    format_help_video,
    format_help_music,
    format_help_info,
    premium_panel,
    format_user_id,
    styled_text
)
from utils.logger import logger
from pathlib import Path
from aiogram.types import FSInputFile

# Link regex pattern
LINK_RE = re.compile(r"https?://\S+")

# ═══════════════════════════════════════════════════════════
# START COMMAND
# ═══════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def start_command(m: Message):
    """Start command with image and clickable user mention - registers user"""
    logger.info(f"START: User {m.from_user.id}")
    
    # Import user state manager
    from utils.user_state import user_state_manager
    
    # Register user as started
    await user_state_manager.mark_user_started(m.from_user.id)
    
    # Mark user as unblocked (in case they were blocked before)
    await user_state_manager.mark_user_unblocked(m.from_user.id)
    
    # Try to send with picture
    picture_path = Path("assets/picture.png")
    
    caption = format_welcome(m.from_user, m.from_user.id)
    
    # Add registration confirmation if started from Spotify link
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
    
    # Fallback to text only
    await m.reply(caption, parse_mode="HTML")

# ═══════════════════════════════════════════════════════════
# HELP COMMAND
# ═══════════════════════════════════════════════════════════

@dp.message(Command("help"))
async def help_command(m: Message):
    """Help command with styled sections"""
    logger.info(f"HELP: User {m.from_user.id}")
    
    # Send 3 separate quoted blocks
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
# LINK HANDLER
# ═══════════════════════════════════════════════════════════

@dp.message(F.text.regexp(LINK_RE))
async def handle_link(m: Message):
    """Route incoming links to appropriate downloader"""
    url = m.text.strip()
    
    logger.info(f"LINK: {url[:50]}... from user {m.from_user.id}")
    
    # Delete user's link after 5 seconds (except Spotify)
    if "spotify.com" not in url.lower():
        async def delete_link_later():
            await asyncio.sleep(5)
            try:
                await m.delete()
                logger.info("Deleted user's link")
            except:
                pass
        
        asyncio.create_task(delete_link_later())
    
    try:
        # Route to appropriate handler
        if "instagram.com" in url.lower():
            await handle_instagram(m, url)
        elif "youtube.com" in url.lower() or "youtu.be" in url.lower():
            await handle_youtube(m, url)
        elif "pinterest.com" in url.lower() or "pin.it" in url.lower():
            await handle_pinterest(m, url)
        elif "spotify.com" in url.lower():
            await handle_spotify_playlist(m, url)
        else:
            await m.answer("Unsupported platform")
    except Exception as e:
        logger.error(f"Error handling link: {e}")
        await m.answer(f"Download failed\n{str(e)[:100]}")

def register_download_handlers():
    """Register download handlers - called from main"""
    logger.info("Download handlers registered")
