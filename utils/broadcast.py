"""
Broadcast system — admin-only mass messaging with rate limiting.
Sends to all private users and group chats.
Handles blocked users gracefully, pins in groups if possible.
"""
import asyncio
import time
from typing import Optional, Tuple
from aiogram import Bot
from aiogram.types import Message
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramBadRequest,
    TelegramRetryAfter,
)
from utils.redis_client import redis_client
from utils.logger import logger
from core.config import config

# ─── Redis key helpers ────────────────────────────────────────────────────────

USERS_SET_KEY = "broadcast:users"       # Set of private user IDs
GROUPS_SET_KEY = "broadcast:groups"     # Set of group chat IDs

async def register_user(user_id: int):
    """Register a private user for broadcasts"""
    await redis_client.sadd(USERS_SET_KEY, str(user_id))

async def register_group(chat_id: int):
    """Register a group chat for broadcasts"""
    await redis_client.sadd(GROUPS_SET_KEY, str(chat_id))

async def unregister_user(user_id: int):
    """Remove user from broadcast list (blocked bot)"""
    await redis_client.srem(USERS_SET_KEY, str(user_id))

async def get_all_users() -> list:
    """Get all registered private user IDs"""
    members = await redis_client.smembers(USERS_SET_KEY)
    result = []
    for m in members:
        try:
            result.append(int(m))
        except (ValueError, TypeError):
            pass
    return result

async def get_all_groups() -> list:
    """Get all registered group chat IDs"""
    members = await redis_client.smembers(GROUPS_SET_KEY)
    result = []
    for m in members:
        try:
            result.append(int(m))
        except (ValueError, TypeError):
            pass
    return result

# ─── Broadcast engine ─────────────────────────────────────────────────────────

async def _send_one(
    bot: Bot,
    chat_id: int,
    text: Optional[str] = None,
    reply_to_msg: Optional[Message] = None,
    pin: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Send one broadcast message to a chat.
    Returns (success, error_reason).
    """
    try:
        if reply_to_msg:
            # Forward/copy the media message
            sent = await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=reply_to_msg.chat.id,
                message_id=reply_to_msg.message_id
            )
        else:
            sent = await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        
        # Try to pin in groups
        if pin and sent:
            try:
                await bot.pin_chat_message(
                    chat_id=chat_id,
                    message_id=sent.message_id,
                    disable_notification=True
                )
            except Exception:
                pass  # Silently ignore pin failures
        
        return True, None
    
    except TelegramForbiddenError:
        return False, "blocked"
    except TelegramBadRequest as e:
        return False, f"bad_request:{str(e)[:50]}"
    except TelegramRetryAfter as e:
        # Respect flood control
        await asyncio.sleep(e.retry_after + 1)
        return False, f"retry_after:{e.retry_after}"
    except Exception as e:
        return False, str(e)[:80]

async def run_broadcast(
    bot: Bot,
    admin_id: int,
    text: Optional[str] = None,
    reply_to_msg: Optional[Message] = None
) -> dict:
    """
    Run a full broadcast to all users and groups.
    Runs in background — returns stats dict when complete.
    
    Args:
        bot: Bot instance
        admin_id: Admin user ID (for delivery report)
        text: Text message to broadcast (or None if media)
        reply_to_msg: Message to copy (for media broadcasts)
    
    Returns:
        dict with stats: total_users, total_groups, success, failed
    """
    users = await get_all_users()
    groups = await get_all_groups()
    
    total_users = len(users)
    total_groups = len(groups)
    success = 0
    failed = 0
    blocked_users = []
    
    logger.info(f"Broadcast started: {total_users} users, {total_groups} groups")
    
    # Send to private users
    for user_id in users:
        ok, reason = await _send_one(bot, user_id, text=text, reply_to_msg=reply_to_msg)
        if ok:
            success += 1
        else:
            failed += 1
            if reason == "blocked":
                blocked_users.append(user_id)
        
        # Rate limiting: ~20 messages/sec
        await asyncio.sleep(config.BROADCAST_RATE_LIMIT)
    
    # Remove blocked users from list
    for uid in blocked_users:
        await unregister_user(uid)
    
    # Send to groups (with pin attempt)
    for chat_id in groups:
        ok, reason = await _send_one(
            bot, chat_id,
            text=text,
            reply_to_msg=reply_to_msg,
            pin=True
        )
        if ok:
            success += 1
        else:
            failed += 1
        
        await asyncio.sleep(config.BROADCAST_RATE_LIMIT)
    
    stats = {
        "total_users": total_users,
        "total_groups": total_groups,
        "success": success,
        "failed": failed,
        "blocked_removed": len(blocked_users)
    }
    
    logger.info(f"Broadcast complete: {stats}")
    
    # Send delivery report to admin
    try:
        report = (
            f"📊 <b>Broadcast Report</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Users: <code>{total_users}</code>\n"
            f"👥 Groups: <code>{total_groups}</code>\n"
            f"✅ Delivered: <code>{success}</code>\n"
            f"❌ Failed: <code>{failed}</code>\n"
            f"🚫 Blocked (removed): <code>{len(blocked_users)}</code>"
        )
        await bot.send_message(admin_id, report, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Could not send broadcast report to admin: {e}")
    
    return stats
