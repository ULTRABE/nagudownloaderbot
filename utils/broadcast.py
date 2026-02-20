"""
Broadcast system — admin-only mass messaging.

Features:
  - Send to all private users + all groups
  - Handle blocked/deactivated users silently (remove from list)
  - Semaphore to avoid flood limits (max 20 msg/sec)
  - TelegramRetryAfter: respect retry_after delay
  - Pin in groups (ignore failure silently)
  - Delivery report sent to admin (total sent, failed, blocked removed)
  - Runs in background (non-blocking)
  - Safe iteration — snapshot list before iterating
  - In-memory fallback when Redis is unavailable
"""
import asyncio
from typing import Optional, Tuple, List, Set
from aiogram import Bot
from aiogram.types import Message
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramBadRequest,
    TelegramRetryAfter,
    TelegramNotFound,
)
from utils.redis_client import redis_client
from utils.logger import logger
from core.config import config
from ui.formatting import format_broadcast_report

# ─── Redis keys ───────────────────────────────────────────────────────────────

USERS_SET_KEY  = "broadcast:users"
GROUPS_SET_KEY = "broadcast:groups"

# ─── In-memory fallback (when Redis is unavailable) ───────────────────────────
_mem_users: Set[int] = set()
_mem_groups: Set[int] = set()

# ─── Semaphore for flood control ──────────────────────────────────────────────
# Telegram allows ~30 messages/sec globally; we use 20 to be safe
_BROADCAST_SEMAPHORE = asyncio.Semaphore(20)

# ─── Registration ─────────────────────────────────────────────────────────────

async def register_user(user_id: int):
    """Register private user for broadcasts"""
    _mem_users.add(user_id)  # Always add to memory
    try:
        await redis_client.sadd(USERS_SET_KEY, str(user_id))
    except Exception as e:
        logger.debug(f"register_user Redis failed (using memory): {e}")

async def register_group(chat_id: int):
    """Register group for broadcasts"""
    _mem_groups.add(chat_id)  # Always add to memory
    try:
        await redis_client.sadd(GROUPS_SET_KEY, str(chat_id))
    except Exception as e:
        logger.debug(f"register_group Redis failed (using memory): {e}")

async def unregister_user(user_id: int):
    """Remove blocked/dead user from broadcast list"""
    _mem_users.discard(user_id)
    try:
        await redis_client.srem(USERS_SET_KEY, str(user_id))
    except Exception as e:
        logger.debug(f"unregister_user Redis failed: {e}")

async def unregister_group(chat_id: int):
    """Remove dead group from broadcast list"""
    _mem_groups.discard(chat_id)
    try:
        await redis_client.srem(GROUPS_SET_KEY, str(chat_id))
    except Exception as e:
        logger.debug(f"unregister_group Redis failed: {e}")

async def get_all_users() -> List[int]:
    """Get snapshot of all registered user IDs (Redis + memory fallback)"""
    result: Set[int] = set(_mem_users)  # Start with memory
    try:
        members = await redis_client.smembers(USERS_SET_KEY)
        for m in members:
            try:
                result.add(int(m))
            except (ValueError, TypeError):
                pass
    except Exception as e:
        logger.debug(f"get_all_users Redis failed (using memory): {e}")
    logger.debug(f"get_all_users: {len(result)} users")
    return list(result)

async def get_all_groups() -> List[int]:
    """Get snapshot of all registered group IDs (Redis + memory fallback)"""
    result: Set[int] = set(_mem_groups)  # Start with memory
    try:
        members = await redis_client.smembers(GROUPS_SET_KEY)
        for m in members:
            try:
                result.add(int(m))
            except (ValueError, TypeError):
                pass
    except Exception as e:
        logger.debug(f"get_all_groups Redis failed (using memory): {e}")
    logger.debug(f"get_all_groups: {len(result)} groups")
    return list(result)

# ─── Send one message ─────────────────────────────────────────────────────────

async def _send_one(
    bot: Bot,
    chat_id: int,
    text: Optional[str] = None,
    reply_to_msg: Optional[Message] = None,
    pin: bool = False,
) -> Tuple[bool, Optional[str]]:
    """
    Send one broadcast message with flood control.
    Returns (success, error_reason).
    """
    async with _BROADCAST_SEMAPHORE:
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

        except TelegramRetryAfter as e:
            # Respect flood control — wait and retry once
            wait_time = e.retry_after + 1
            logger.warning(f"Broadcast flood control: waiting {wait_time}s for chat {chat_id}")
            await asyncio.sleep(wait_time)
            try:
                if reply_to_msg:
                    await bot.copy_message(
                        chat_id=chat_id,
                        from_chat_id=reply_to_msg.chat.id,
                        message_id=reply_to_msg.message_id,
                    )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode="HTML",
                    )
                return True, None
            except Exception as retry_e:
                return False, f"retry_failed:{str(retry_e)[:50]}"

        except TelegramForbiddenError:
            return False, "blocked"
        except TelegramNotFound:
            return False, "not_found"
        except TelegramBadRequest as e:
            return False, f"bad_request:{str(e)[:50]}"
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

    Safety:
    - Snapshot user/group lists before iterating (safe iteration)
    - Remove blocked/dead users automatically
    - Semaphore prevents flood
    - Rate limit between messages
    """
    # Snapshot lists before iterating — safe against concurrent modifications
    users  = await get_all_users()
    groups = await get_all_groups()

    total_users  = len(users)
    total_groups = len(groups)
    success = 0
    failed  = 0
    blocked_users: List[int] = []
    dead_groups: List[int] = []

    logger.info(f"Broadcast started: {total_users} users, {total_groups} groups, text={bool(text)}, media={bool(reply_to_msg)}")
    if total_users == 0 and total_groups == 0:
        logger.warning("Broadcast: no users or groups registered — nothing to send")
        try:
            await bot.send_message(
                admin_id,
                "📢 <b>Broadcast</b>\n\nNo users or groups registered yet.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return {"total_users": 0, "total_groups": 0, "success": 0, "failed": 0, "blocked_removed": 0}

    # Send to private users
    for user_id in users:
        try:
            ok, reason = await _send_one(bot, user_id, text=text, reply_to_msg=reply_to_msg)
            if ok:
                success += 1
            else:
                failed += 1
                if reason in ("blocked", "not_found"):
                    blocked_users.append(user_id)
                    logger.debug(f"Broadcast: removing dead user {user_id} ({reason})")
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast user {user_id} error: {e}")
        await asyncio.sleep(config.BROADCAST_RATE_LIMIT)

    # Remove blocked/dead users automatically
    for uid in blocked_users:
        await unregister_user(uid)

    if blocked_users:
        logger.info(f"Broadcast: removed {len(blocked_users)} dead users")

    # Send to groups (with pin attempt)
    for chat_id in groups:
        try:
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
                if reason in ("blocked", "not_found"):
                    dead_groups.append(chat_id)
                    logger.debug(f"Broadcast: removing dead group {chat_id} ({reason})")
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast group {chat_id} error: {e}")
        await asyncio.sleep(config.BROADCAST_RATE_LIMIT)

    # Remove dead groups automatically
    for gid in dead_groups:
        await unregister_group(gid)

    if dead_groups:
        logger.info(f"Broadcast: removed {len(dead_groups)} dead groups")

    stats = {
        "total_users":  total_users,
        "total_groups": total_groups,
        "success":      success,
        "failed":       failed,
        "blocked_removed": len(blocked_users) + len(dead_groups),
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
