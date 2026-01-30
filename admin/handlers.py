"""Admin command handlers"""
import asyncio
from aiogram import F
from aiogram.filters import Command
from aiogram.types import Message

from core.bot import bot, dp
from admin.permissions import permission_manager
from admin.moderation import moderation_manager
from admin.filters import filter_manager
from ui.formatting import (
    format_admin_action,
    format_error,
    premium_panel,
    mention,
    format_user_id
)
from utils.logger import logger

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
        "User Details",
        f"  First Name: {user.first_name}",
        f"  Last Name: {user.last_name}" if user.last_name else "  Last Name: None",
        f"  Username: @{user.username}" if user.username else "  Username: None",
        f"  ID: {format_user_id(user.id)}",
        f"  Language: {user.language_code}" if user.language_code else "  Language: Unknown",
        "",
        "Chat Details",
        f"  Chat: {chat_title}",
        f"  Type: {m.chat.type}",
        f"  ID: {format_user_id(m.chat.id)}"
    ]
    await m.reply(premium_panel("Your Information", lines), parse_mode="HTML")

# ═══════════════════════════════════════════════════════════
# ADMIN MANAGEMENT
# ═══════════════════════════════════════════════════════════

@dp.message(Command("promote"))
async def cmd_promote(m: Message):
    """Promote user to admin"""
    if m.chat.type == "private":
        await m.reply(format_error("Invalid Context", "This command only works in groups"), parse_mode="HTML")
        return
    
    # Check if sender is admin
    if not await permission_manager.is_admin(bot, m.chat.id, m.from_user.id):
        await m.reply(format_error("Permission Denied", "You must be an admin"), parse_mode="HTML")
        return
    
    if not m.reply_to_message:
        await m.reply(format_error("Invalid Usage", "Reply to a user to promote them"), parse_mode="HTML")
        return
    
    target_user = m.reply_to_message.from_user
    await permission_manager.add_bot_admin(m.chat.id, target_user.id)
    
    await m.reply(
        format_admin_action("Promote", target_user, "User promoted to admin"),
        parse_mode="HTML"
    )

@dp.message(Command("demote"))
async def cmd_demote(m: Message):
    """Demote admin"""
    if m.chat.type == "private":
        await m.reply(format_error("Invalid Context", "This command only works in groups"), parse_mode="HTML")
        return
    
    # Check if sender is admin
    if not await permission_manager.is_admin(bot, m.chat.id, m.from_user.id):
        await m.reply(format_error("Permission Denied", "You must be an admin"), parse_mode="HTML")
        return
    
    if not m.reply_to_message:
        await m.reply(format_error("Invalid Usage", "Reply to a user to demote them"), parse_mode="HTML")
        return
    
    target_user = m.reply_to_message.from_user
    await permission_manager.remove_bot_admin(m.chat.id, target_user.id)
    
    await m.reply(
        format_admin_action("Demote", target_user, "User demoted to regular user"),
        parse_mode="HTML"
    )

# ═══════════════════════════════════════════════════════════
# MODERATION COMMANDS
# ═══════════════════════════════════════════════════════════

@dp.message(Command("mute"))
async def cmd_mute(m: Message):
    """Mute user"""
    if m.chat.type == "private":
        await m.reply(format_error("Invalid Context", "This command only works in groups"), parse_mode="HTML")
        return
    
    if not await permission_manager.is_admin(bot, m.chat.id, m.from_user.id):
        await m.reply(format_error("Permission Denied", "You must be an admin"), parse_mode="HTML")
        return
    
    if not m.reply_to_message:
        await m.reply(format_error("Invalid Usage", "Reply to a user to mute them\nUsage: /mute [minutes]"), parse_mode="HTML")
        return
    
    target_user = m.reply_to_message.from_user
    
    # Parse duration
    duration = 0  # Permanent by default
    args = m.text.split()
    if len(args) > 1:
        try:
            duration = int(args[1])
        except:
            pass
    
    success, message = await moderation_manager.mute_user(bot, m.chat.id, target_user.id, duration)
    
    if success:
        await m.reply(
            format_admin_action("Mute", target_user, f"Duration: {message}"),
            parse_mode="HTML"
        )
    else:
        await m.reply(format_error("Mute Failed", message), parse_mode="HTML")

@dp.message(Command("unmute"))
async def cmd_unmute(m: Message):
    """Unmute user"""
    if m.chat.type == "private":
        await m.reply(format_error("Invalid Context", "This command only works in groups"), parse_mode="HTML")
        return
    
    if not await permission_manager.is_admin(bot, m.chat.id, m.from_user.id):
        await m.reply(format_error("Permission Denied", "You must be an admin"), parse_mode="HTML")
        return
    
    if not m.reply_to_message:
        await m.reply(format_error("Invalid Usage", "Reply to a user to unmute them"), parse_mode="HTML")
        return
    
    target_user = m.reply_to_message.from_user
    success, message = await moderation_manager.unmute_user(bot, m.chat.id, target_user.id)
    
    if success:
        await m.reply(
            format_admin_action("Unmute", target_user, "User can now send messages"),
            parse_mode="HTML"
        )
    else:
        await m.reply(format_error("Unmute Failed", message), parse_mode="HTML")

@dp.message(Command("ban"))
async def cmd_ban(m: Message):
    """Ban user"""
    if m.chat.type == "private":
        await m.reply(format_error("Invalid Context", "This command only works in groups"), parse_mode="HTML")
        return
    
    if not await permission_manager.is_admin(bot, m.chat.id, m.from_user.id):
        await m.reply(format_error("Permission Denied", "You must be an admin"), parse_mode="HTML")
        return
    
    if not m.reply_to_message:
        await m.reply(format_error("Invalid Usage", "Reply to a user to ban them"), parse_mode="HTML")
        return
    
    target_user = m.reply_to_message.from_user
    success, message = await moderation_manager.ban_user(bot, m.chat.id, target_user.id)
    
    if success:
        await m.reply(
            format_admin_action("Ban", target_user, "User banned from chat"),
            parse_mode="HTML"
        )
    else:
        await m.reply(format_error("Ban Failed", message), parse_mode="HTML")

@dp.message(Command("unban"))
async def cmd_unban(m: Message):
    """Unban user"""
    if m.chat.type == "private":
        await m.reply(format_error("Invalid Context", "This command only works in groups"), parse_mode="HTML")
        return
    
    if not await permission_manager.is_admin(bot, m.chat.id, m.from_user.id):
        await m.reply(format_error("Permission Denied", "You must be an admin"), parse_mode="HTML")
        return
    
    if not m.reply_to_message:
        await m.reply(format_error("Invalid Usage", "Reply to a user to unban them"), parse_mode="HTML")
        return
    
    target_user = m.reply_to_message.from_user
    success, message = await moderation_manager.unban_user(bot, m.chat.id, target_user.id)
    
    if success:
        await m.reply(
            format_admin_action("Unban", target_user, "User can now rejoin chat"),
            parse_mode="HTML"
        )
    else:
        await m.reply(format_error("Unban Failed", message), parse_mode="HTML")

# ═══════════════════════════════════════════════════════════
# FILTER COMMANDS
# ═══════════════════════════════════════════════════════════

@dp.message(Command("filter"))
async def cmd_filter(m: Message):
    """Add word to filter list"""
    if m.chat.type == "private":
        await m.reply(format_error("Invalid Context", "This command only works in groups"), parse_mode="HTML")
        return
    
    if not await permission_manager.is_admin(bot, m.chat.id, m.from_user.id):
        await m.reply(format_error("Permission Denied", "You must be an admin"), parse_mode="HTML")
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.reply(format_error("Invalid Usage", "Usage: /filter <word>"), parse_mode="HTML")
        return
    
    word = args[1].strip()
    success = await filter_manager.add_filter(m.chat.id, word)
    
    if success:
        lines = [f"Word: {word}", "Type: Substring filter", "Status: Active"]
        await m.reply(premium_panel("Filter Added", lines), parse_mode="HTML")
    else:
        await m.reply(format_error("Filter Failed", "Could not add filter"), parse_mode="HTML")

@dp.message(Command("unfilter"))
async def cmd_unfilter(m: Message):
    """Remove word from filter list"""
    if m.chat.type == "private":
        await m.reply(format_error("Invalid Context", "This command only works in groups"), parse_mode="HTML")
        return
    
    if not await permission_manager.is_admin(bot, m.chat.id, m.from_user.id):
        await m.reply(format_error("Permission Denied", "You must be an admin"), parse_mode="HTML")
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.reply(format_error("Invalid Usage", "Usage: /unfilter <word>"), parse_mode="HTML")
        return
    
    word = args[1].strip()
    success = await filter_manager.remove_filter(m.chat.id, word)
    
    if success:
        lines = [f"Word: {word}", "Status: Removed"]
        await m.reply(premium_panel("Filter Removed", lines), parse_mode="HTML")
    else:
        await m.reply(format_error("Unfilter Failed", "Could not remove filter"), parse_mode="HTML")

@dp.message(Command("filters"))
async def cmd_filters(m: Message):
    """List all filters"""
    if m.chat.type == "private":
        await m.reply(format_error("Invalid Context", "This command only works in groups"), parse_mode="HTML")
        return
    
    filters = await filter_manager.get_filters(m.chat.id)
    
    if not filters:
        await m.reply(premium_panel("Active Filters", ["No filters configured"]), parse_mode="HTML")
    else:
        lines = [f"  • {word}" for word in sorted(filters)]
        lines.insert(0, f"Total: {len(filters)} filters")
        await m.reply(premium_panel("Active Filters", lines), parse_mode="HTML")

@dp.message(Command("block"))
async def cmd_block(m: Message):
    """Add word to blocklist"""
    if m.chat.type == "private":
        await m.reply(format_error("Invalid Context", "This command only works in groups"), parse_mode="HTML")
        return
    
    if not await permission_manager.is_admin(bot, m.chat.id, m.from_user.id):
        await m.reply(format_error("Permission Denied", "You must be an admin"), parse_mode="HTML")
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.reply(format_error("Invalid Usage", "Usage: /block <word>"), parse_mode="HTML")
        return
    
    word = args[1].strip()
    success = await filter_manager.add_to_blocklist(m.chat.id, word)
    
    if success:
        lines = [f"Word: {word}", "Type: Exact match block", "Status: Active"]
        await m.reply(premium_panel("Word Blocked", lines), parse_mode="HTML")
    else:
        await m.reply(format_error("Block Failed", "Could not add to blocklist"), parse_mode="HTML")

@dp.message(Command("unblock"))
async def cmd_unblock(m: Message):
    """Remove word from blocklist"""
    if m.chat.type == "private":
        await m.reply(format_error("Invalid Context", "This command only works in groups"), parse_mode="HTML")
        return
    
    if not await permission_manager.is_admin(bot, m.chat.id, m.from_user.id):
        await m.reply(format_error("Permission Denied", "You must be an admin"), parse_mode="HTML")
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.reply(format_error("Invalid Usage", "Usage: /unblock <word>"), parse_mode="HTML")
        return
    
    word = args[1].strip()
    success = await filter_manager.remove_from_blocklist(m.chat.id, word)
    
    if success:
        lines = [f"Word: {word}", "Status: Unblocked"]
        await m.reply(premium_panel("Word Unblocked", lines), parse_mode="HTML")
    else:
        await m.reply(format_error("Unblock Failed", "Could not remove from blocklist"), parse_mode="HTML")

@dp.message(Command("blocklist"))
async def cmd_blocklist(m: Message):
    """List all blocked words"""
    if m.chat.type == "private":
        await m.reply(format_error("Invalid Context", "This command only works in groups"), parse_mode="HTML")
        return
    
    blocklist = await filter_manager.get_blocklist(m.chat.id)
    
    if not blocklist:
        await m.reply(premium_panel("Blocked Words", ["No words blocked"]), parse_mode="HTML")
    else:
        lines = [f"  • {word}" for word in sorted(blocklist)]
        lines.insert(0, f"Total: {len(blocklist)} blocked")
        await m.reply(premium_panel("Blocked Words", lines), parse_mode="HTML")

# ═══════════════════════════════════════════════════════════
# WHISPER COMMAND
# ═══════════════════════════════════════════════════════════

@dp.message(Command("whisper"))
async def cmd_whisper(m: Message):
    """Send private message to user"""
    if m.chat.type == "private":
        await m.reply(format_error("Invalid Context", "This command only works in groups"), parse_mode="HTML")
        return
    
    if not m.reply_to_message:
        await m.reply(format_error("Invalid Usage", "Reply to a user with /whisper <message>"), parse_mode="HTML")
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.reply(format_error("Invalid Usage", "Usage: /whisper <message>"), parse_mode="HTML")
        return
    
    # Delete command message immediately
    try:
        await m.delete()
    except:
        pass
    
    target_user = m.reply_to_message.from_user
    whisper_text = args[1].strip()
    
    # Send whisper to target user's DM
    try:
        lines = [
            f"From: {mention(m.from_user)}",
            f"Chat: {m.chat.title}",
            "",
            f"Message:",
            f"  {whisper_text}"
        ]
        await bot.send_message(
            target_user.id,
            premium_panel("Private Whisper", lines),
            parse_mode="HTML"
        )
        logger.info(f"Whisper sent from {m.from_user.id} to {target_user.id}")
    except Exception as e:
        logger.error(f"Failed to send whisper: {e}")

def register_admin_handlers():
    """Register admin handlers - called from main"""
    logger.info("Admin handlers registered")
