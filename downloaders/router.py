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
    format_help_admin,
    format_help_filters
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
    """Start command with image and clickable user mention"""
    logger.info(f"START: User {m.from_user.id}")
    
    # Try to send with picture
    picture_path = Path("assets/picture.png")
    
    caption = format_welcome(m.from_user, m.from_user.id)
    
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
    """Help command with 5 premium quoted blocks"""
    logger.info(f"HELP: User {m.from_user.id}")
    
    # Send 5 separate quoted blocks
    await m.reply(format_help_video(), parse_mode="HTML")
    await asyncio.sleep(0.2)
    
    await m.reply(format_help_music(), parse_mode="HTML")
    await asyncio.sleep(0.2)
    
    await m.reply(format_help_info(), parse_mode="HTML")
    await asyncio.sleep(0.2)
    
    await m.reply(format_help_admin(), parse_mode="HTML")
    await asyncio.sleep(0.2)
    
    await m.reply(format_help_filters(), parse_mode="HTML")

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
