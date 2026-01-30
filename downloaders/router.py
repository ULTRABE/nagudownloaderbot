"""Download router - routes URLs to appropriate handlers"""
import asyncio
import re
from aiogram import F
from aiogram.types import Message

from core.bot import dp
from .instagram import handle_instagram
from .pinterest import handle_pinterest
from .youtube import handle_youtube
from .spotify import handle_spotify_playlist
from utils.logger import logger

# Link regex pattern
LINK_RE = re.compile(r"https?://\S+")

@dp.message(F.text.regexp(LINK_RE))
async def handle_link(m: Message):
    """Route incoming links to appropriate downloader"""
    url = m.text.strip()
    
    # Delete user's link after 5 seconds (for non-Spotify links)
    if "spotify.com" not in url.lower():
        async def delete_link_later():
            await asyncio.sleep(5)
            try:
                await m.delete()
                logger.info("Deleted user's link after 5s")
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
            await m.answer("❌ 𝐔𝐧𝐬𝐮𝐩𝐩𝐨𝐫𝐭𝐞𝐝 𝐏𝐥𝐚𝐭𝐟𝐨𝐫𝐦")
    except Exception as e:
        logger.error(f"Error handling link: {e}")
        await m.answer(f"❌ 𝐄𝐫𝐫𝐨𝐫\n{str(e)[:100]}")

def register_download_handlers():
    """Register download handlers - called from main"""
    logger.info("Download handlers registered")
