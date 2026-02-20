"""
Optional Premium Sticker System.

Stickers are sent when a link is received, then deleted after media delivery.
If a sticker fails to send → ignore silently. Bot works without stickers.

Never send stickers in DM playlist mode.
"""
import os

# Sticker file IDs — override via env vars or set directly here
STICKERS: dict = {
    "youtube":   os.getenv("YT_STICKER",   "CAACAgIAAxkBAAEaedlpez9LOhwF-tARQsD1V9jzU8iw1gACQjcAAgQyMEixyZ896jTkCDgE"),
    "instagram": os.getenv("IG_STICKER",   "CAACAgIAAxkBAAEadEdpekZa1-2qYm-1a3dX0JmM_Z9uDgAC4wwAAjAT0Euml6TE9QhYWzgE"),
    "pinterest": os.getenv("PIN_STICKER",  "CAACAgIAAxkBAAEaegZpe0KJMDIkiCbudZrXhJDwBXYHqgACExIAAq3mUUhZ4G5Cm78l2DgE"),
    "music":     os.getenv("MUSIC_STICKER","CAACAgIAAxkBAAEaegZpe0KJMDIkiCbudZrXhJDwBXYHqgACExIAAq3mUUhZ4G5Cm78l2DgE"),
}

# Set to False to disable all stickers globally
STICKERS_ENABLED: bool = True


async def send_sticker(bot, chat_id: int, platform: str) -> int | None:
    """
    Send a sticker for the given platform.
    Returns message_id on success, None on failure.
    Fails silently — never raises.
    """
    if not STICKERS_ENABLED:
        return None
    sticker_id = STICKERS.get(platform)
    if not sticker_id:
        return None
    try:
        msg = await bot.send_sticker(chat_id, sticker_id)
        return msg.message_id
    except Exception:
        return None


async def delete_sticker(bot, chat_id: int, message_id: int | None):
    """
    Delete a previously sent sticker message.
    Fails silently — never raises.
    """
    if message_id is None:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass
