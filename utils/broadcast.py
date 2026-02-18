"""
Broadcast system — admin-only mass messaging.

Features:
  - Send to all private users + all groups
  - Handle blocked users silently (remove from list)
  - Rate limit: ~20 messages/sec
  - Pin in groups (ignore failure silently)
  - Delivery report sent to admin
  - Runs in background (non-blocking)
"""
import asyncio
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
from ui.formatting import format_broadcast_report

# ─── Redis keys ───────────────────────────────────────────────────────────────

USERS_SET_KEY  = "broadcast:users"
GROUPS_SET_KEY = "broadcast:groups"

# ─── Registration ─────────────────────────────────────────────────────────────

async def register_user(user_id: int):
    """Register private user for broadcasts"""
    await redis_client.sadd(USERS_SET_KEY, str(user_id))

async def register_group(chat_id: int):
    """Register group for broadcasts"""
    await redis_client.sadd(GROUPS_SET_KEY, str(chat_id))

async def unregister_user(user_id: int):
    """Remove blocked user from broadcast list"""
    await redis_client.srem(USERS_SET_KEY, str(user_id))

async def get_all_users() -> list:
    members = await redis_client.smembers(USERS_SET_KEY)
    result = []
    for m in members:
        try:
            result.append(int(m))
        except (ValueError, TypeError):
            pass
    return result

async def get_all_groups() -> list:
    members = await redis_client.smembers(GROUPS_SET_KEY)
    result = []
    for m in members:
        try:
            result.append(int(m))
        except (ValueError, TypeError):
            pass
    return result

# ─── Send one message ─────────────────────────────────────────────────────────

async def _send_one(
    bot: Bot,
    chat_id: int,
    text: Optional[str] = None,
    reply_to_msg: Optional[Message] = None,
    pin: bool = False,
) -> Tuple[bool, Optional[str]]:
    """
    Send one broadcast message.
    Returns (success, error_reason).
    """
    try:
        if reply_to_msg:
            sent = await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=reply_to_msg.chat.id,
                message_id=reply_to_msg.message_id,
            )
        else:
            sent = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
            )

        # Pin in groups — ignore failure silently
        if pin and sent:
            try:
                await bot.pin_chat_message(
                    chat_id=chat_id,
                    message_id=sent.message_id,
                    disable_notification=True,
                )
            except Exception:
                pass

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

# ─── Broadcast engine ─────────────────────────────────────────────────────────

async def run_broadcast(
    bot: Bot,
    admin_id: int,
    text: Optional[str] = None,
    reply_to_msg: Optional[Message] = None,
) -> dict:
    """
    Run full broadcast to all users and groups.
    Runs in background — sends delivery report to admin when done.
    """
    users  = await get_all_users()
    groups = await get_all_groups()

    total_users  = len(users)
    total_groups = len(groups)
    success = 0
    failed  = 0
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
        await asyncio.sleep(config.BROADCAST_RATE_LIMIT)

    # Remove blocked users
    for uid in blocked_users:
        await unregister_user(uid)

    # Send to groups (with pin attempt)
    for chat_id in groups:
        ok, reason = await _send_one(
            bot, chat_id,
            text=text,
            reply_to_msg=reply_to_msg,
            pin=True,
        )
        if ok:
            success += 1
        else:
            failed += 1
        await asyncio.sleep(config.BROADCAST_RATE_LIMIT)

    stats = {
        "total_users":  total_users,
        "total_groups": total_groups,
        "success":      success,
        "failed":       failed,
        "blocked_removed": len(blocked_users),
    }

    logger.info(f"Broadcast complete: {stats}")

    # Send delivery report to admin
    try:
        await bot.send_message(
            admin_id,
            format_broadcast_report(total_users, total_groups, success, failed),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Could not send broadcast report: {e}")

    return stats
