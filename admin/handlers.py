"""Admin command handlers"""
import asyncio
from datetime import datetime, timedelta
from aiogram import F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, ChatPermissions
from pathlib import Path

from core.bot import bot, dp
from .permissions import is_admin, is_telegram_admin, add_admin, remove_admin
from .moderation import mute_user, unmute_user
from .filters import (
    add_filter, remove_filter, get_filters,
    add_to_blocklist, remove_from_blocklist, get_blocklist,
    check_message_filters
)
from utils.helpers import mention
from utils.logger import logger

# ═══════════════════════════════════════════════════════════
# START & HELP COMMANDS
# ═══════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def start_command(m: Message):
    """Start command handler"""
    username = f"@{m.from_user.username}" if m.from_user.username else "𝘕𝘰 𝘜𝘴𝘦𝘳𝘯𝘢𝘮𝘦"
    
    caption = f"""
╭─ ✨ 𝗡𝗔𝗚𝗨 𝗗𝗢𝗪𝗡𝗟𝗢𝗔𝗗𝗘𝗥 𝗕𝗢𝗧
│
│ 👤 𝘜𝘴𝘦𝘳 𝘐𝘯𝘧𝘰𝘳𝘮𝘢𝘵𝘪𝘰𝘯
│ ▸ 𝘐𝘋: {m.from_user.id}
│ ▸ 𝘜𝘴𝘦𝘳: {username}
│ ▸ 𝘕𝘢𝘮𝘦: {m.from_user.first_name}
│
│ ⚡ 𝘘𝘶𝘪𝘤𝘬 𝘊𝘰𝘮𝘮𝘢𝘯𝘥𝘴
│ ▸ /help ⟶ 𝘝𝘪𝘦𝘸 𝘢𝘭𝘭 𝘧𝘦𝘢𝘵𝘶𝘳𝘦𝘴
│ ▸ /mp3 ⟶ 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥 𝘮𝘶𝘴𝘪𝘤
│ ▸ 𝘚𝘦𝘯𝘥 𝘢𝘯𝘺 𝘭𝘪𝘯𝘬 𝘵𝘰 𝘥𝘰𝘸𝘯𝘭𝘰𝘢𝘥
│
╰─ 💎 𝘖𝘸𝘯𝘦𝘳: @bhosadih"""
    
    # Try to send with picture
    picture_path = Path("assets/picture.png")
    if picture_path.exists():
        try:
            from aiogram.types import FSInputFile
            await m.reply_photo(FSInputFile(picture_path), caption=caption)
            return
        except Exception as e:
            logger.error(f"Failed to send picture: {e}")
    
    # Fallback to text only
    await m.reply(caption)

@dp.message(Command("help"))
async def help_command(m: Message):
    """Help command handler"""
    await m.reply("""
╭─ ✨ 𝗕𝗢𝗧 𝗙𝗘𝗔𝗧𝗨𝗥𝗘𝗦 & 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦
│
│ 📥 𝘝𝘪𝘥𝘦𝘰 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥
│ ▸ 𝘐𝘯𝘴𝘵𝘢𝘨𝘳𝘢𝘮 ⟶ 𝘗𝘰𝘴𝘵𝘴, 𝘙𝘦𝘦𝘭𝘴, 𝘚𝘵𝘰𝘳𝘪𝘦𝘴
│ ▸ 𝘠𝘰𝘶𝘛𝘶𝘣𝘦 ⟶ 𝘝𝘪𝘥𝘦𝘰𝘴, 𝘚𝘩𝘰𝘳𝘵𝘴, 𝘚𝘵𝘳𝘦𝘢𝘮𝘴
│ ▸ 𝘗𝘪𝘯𝘵𝘦𝘳𝘦𝘴𝘵 ⟶ 𝘝𝘪𝘥𝘦𝘰 𝘗𝘪𝘯𝘴
│ ➜ 𝘑𝘶𝘴𝘵 𝘴𝘦𝘯𝘥 𝘵𝘩𝘦 𝘭𝘪𝘯𝘬!
│
│ 🎵 𝘔𝘶𝘴𝘪𝘤 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥
│ ▸ /mp3 [𝘴𝘰𝘯𝘨 𝘯𝘢𝘮𝘦] ⟶ 𝘚𝘦𝘢𝘳𝘤𝘩 & 𝘥𝘰𝘸𝘯𝘭𝘰𝘢𝘥
│ ▸ 𝘚𝘱𝘰𝘵𝘪𝘧𝘺 𝘜𝘙𝘓 ⟶ 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥 𝘱𝘭𝘢𝘺𝘭𝘪𝘴𝘵 𝘵𝘰 𝘋𝘔
│
│ ℹ️ 𝘐𝘯𝘧𝘰 𝘊𝘰𝘮𝘮𝘢𝘯𝘥𝘴
│ ▸ /id ⟶ 𝘎𝘦𝘵 𝘶𝘴𝘦𝘳 𝘐𝘋
│ ▸ /chatid ⟶ 𝘎𝘦𝘵 𝘤𝘩𝘢𝘵 𝘐𝘋
│ ▸ /myinfo ⟶ 𝘠𝘰𝘶𝘳 𝘧𝘶𝘭𝘭 𝘪𝘯𝘧𝘰
│
│ 👮 𝘈𝘥𝘮𝘪𝘯 𝘊𝘰𝘮𝘮𝘢𝘯𝘥𝘴
│ ▸ /promote ⟶ 𝘔𝘢𝘬𝘦 𝘶𝘴𝘦𝘳 𝘢𝘥𝘮𝘪𝘯
│ ▸ /demote ⟶ 𝘙𝘦𝘮𝘰𝘷𝘦 𝘢𝘥𝘮𝘪𝘯
│ ▸ /mute [𝘮𝘪𝘯] ⟶ 𝘔𝘶𝘵𝘦 𝘶𝘴𝘦𝘳
│ ▸ /unmute ⟶ 𝘜𝘯𝘮𝘶𝘵𝘦 𝘶𝘴𝘦𝘳
│ ▸ /ban ⟶ 𝘉𝘢𝘯 𝘶𝘴𝘦𝘳
│ ▸ /unban ⟶ 𝘜𝘯𝘣𝘢𝘯 𝘶𝘴𝘦𝘳
│
│ 🛡️ 𝘍𝘪𝘭𝘵𝘦𝘳 𝘊𝘰𝘮𝘮𝘢𝘯𝘥𝘴
│ ▸ /filter <𝘸𝘰𝘳𝘥> ⟶ 𝘍𝘪𝘭𝘵𝘦𝘳 𝘸𝘰𝘳𝘥
│ ▸ /unfilter <𝘸𝘰𝘳𝘥> ⟶ 𝘙𝘦𝘮𝘰𝘷𝘦 𝘧𝘪𝘭𝘵𝘦𝘳
│ ▸ /filters ⟶ 𝘓𝘪𝘴𝘵 𝘢𝘭𝘭 𝘧𝘪𝘭𝘵𝘦𝘳𝘴
│ ▸ /block <𝘸𝘰𝘳𝘥> ⟶ 𝘉𝘭𝘰𝘤𝘬 𝘦𝘹𝘢𝘤𝘵 𝘸𝘰𝘳𝘥
│ ▸ /unblock <𝘸𝘰𝘳𝘥> ⟶ 𝘜𝘯𝘣𝘭𝘰𝘤𝘬 𝘸𝘰𝘳𝘥
│ ▸ /blocklist ⟶ 𝘓𝘪𝘴𝘵 𝘣𝘭𝘰𝘤𝘬𝘦𝘥
│
│ 💬 𝘖𝘵𝘩𝘦𝘳 𝘊𝘰𝘮𝘮𝘢𝘯𝘥𝘴
│ ▸ /whisper <𝘮𝘴𝘨> ⟶ 𝘗𝘳𝘪𝘷𝘢𝘵𝘦 𝘮𝘦𝘴𝘴𝘢𝘨𝘦
│
╰─ 💎 𝘖𝘸𝘯𝘦𝘳: @bhosadih""")

# ═══════════════════════════════════════════════════════════
# INFO COMMANDS
# ═══════════════════════════════════════════════════════════

@dp.message(Command("id"))
async def cmd_id(m: Message):
    """Get user ID"""
    if m.reply_to_message:
        user = m.reply_to_message.from_user
        await m.reply(f"""
╭─ 👤 𝗨𝗦𝗘𝗥 𝗜𝗗 𝗜𝗡𝗙𝗢
│
│ ▸ 𝘕𝘢𝘮𝘦: {user.first_name}
│ ▸ 𝘜𝘴𝘦𝘳𝘯𝘢𝘮𝘦: @{user.username if user.username else '𝘕𝘰𝘯𝘦'}
│ ▸ 𝘐𝘋: `{user.id}`
│
╰──────────────""")
    else:
        await m.reply(f"""
╭─ 👤 𝗬𝗢𝗨𝗥 𝗜𝗗 𝗜𝗡𝗙𝗢
│
│ ▸ 𝘕𝘢𝘮𝘦: {m.from_user.first_name}
│ ▸ 𝘜𝘴𝘦𝘳𝘯𝘢𝘮𝘦: @{m.from_user.username if m.from_user.username else '𝘕𝘰𝘯𝘦'}
│ ▸ 𝘐𝘋: `{m.from_user.id}`
│
╰──────────────""")

@dp.message(Command("chatid"))
async def cmd_chatid(m: Message):
    """Get chat ID"""
    await m.reply(f"""
╭─ 💬 𝗖𝗛𝗔𝗧 𝗜𝗗 𝗜𝗡𝗙𝗢
│
│ ▸ 𝘊𝘩𝘢𝘵: {m.chat.title if m.chat.title else '𝘗𝘳𝘪𝘷𝘢𝘵𝘦 𝘊𝘩𝘢𝘵'}
│ ▸ 𝘛𝘺𝘱𝘦: {m.chat.type}
│ ▸ 𝘐𝘋: `{m.chat.id}`
│
╰──────────────""")

@dp.message(Command("myinfo"))
async def cmd_myinfo(m: Message):
    """Get detailed user info"""
    user = m.from_user
    await m.reply(f"""
╭─ ✨ 𝗬𝗢𝗨𝗥 𝗜𝗡𝗙𝗢𝗥𝗠𝗔𝗧𝗜𝗢𝗡
│
│ 👤 𝘜𝘴𝘦𝘳 𝘋𝘦𝘵𝘢𝘪𝘭𝘴
│ ▸ 𝘍𝘪𝘳𝘴𝘵 𝘕𝘢𝘮𝘦: {user.first_name}
│ ▸ 𝘓𝘢𝘴𝘵 𝘕𝘢𝘮𝘦: {user.last_name if user.last_name else '𝘕𝘰𝘯𝘦'}
│ ▸ 𝘜𝘴𝘦𝘳𝘯𝘢𝘮𝘦: @{user.username if user.username else '𝘕𝘰𝘯𝘦'}
│ ▸ 𝘐𝘋: `{user.id}`
│ ▸ 𝘓𝘢𝘯𝘨𝘶𝘢𝘨𝘦: {user.language_code if user.language_code else '𝘜𝘯𝘬𝘯𝘰𝘸𝘯'}
│
│ 💬 𝘊𝘩𝘢𝘵 𝘋𝘦𝘵𝘢𝘪𝘭𝘴
│ ▸ 𝘊𝘩𝘢𝘵: {m.chat.title if m.chat.title else '𝘗𝘳𝘪𝘷𝘢𝘵𝘦'}
│ ▸ 𝘛𝘺𝘱𝘦: {m.chat.type}
│ ▸ 𝘐𝘋: `{m.chat.id}`
│
╰──────────────""")

# ═══════════════════════════════════════════════════════════
# ADMIN MANAGEMENT
# ═══════════════════════════════════════════════════════════

@dp.message(Command("promote"))
async def cmd_promote(m: Message):
    """Promote user to admin"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    # Check if sender is Telegram admin
    if not await is_telegram_admin(m.chat.id, m.from_user.id):
        await m.reply("[ X ] You must be a Telegram admin to use this command")
        return
    
    if not m.reply_to_message:
        await m.reply("[ ! ] Reply to a user to promote them")
        return
    
    target_user = m.reply_to_message.from_user
    await add_admin(m.chat.id, target_user.id)
    
    await m.reply(f"""
╭─ ✅ 𝗨𝗦𝗘𝗥 𝗣𝗥𝗢𝗠𝗢𝗧𝗘𝗗
│
│ ▸ 𝘜𝘴𝘦𝘳: {target_user.first_name}
│ ▸ 𝘐𝘋: `{target_user.id}`
│ ▸ 𝘚𝘵𝘢𝘵𝘶𝘴: 𝘈𝘥𝘮𝘪𝘯
│
╰──────────────""")

@dp.message(Command("demote"))
async def cmd_demote(m: Message):
    """Demote admin"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    # Check if sender is Telegram admin
    if not await is_telegram_admin(m.chat.id, m.from_user.id):
        await m.reply("[ X ] You must be a Telegram admin to use this command")
        return
    
    if not m.reply_to_message:
        await m.reply("[ ! ] Reply to a user to demote them")
        return
    
    target_user = m.reply_to_message.from_user
    await remove_admin(m.chat.id, target_user.id)
    
    await m.reply(f"""
╭─ ⬇️ 𝗨𝗦𝗘𝗥 𝗗𝗘𝗠𝗢𝗧𝗘𝗗
│
│ ▸ 𝘜𝘴𝘦𝘳: {target_user.first_name}
│ ▸ 𝘐𝘋: `{target_user.id}`
│ ▸ 𝘚𝘵𝘢𝘵𝘶𝘴: 𝘙𝘦𝘨𝘶𝘭𝘢𝘳 𝘜𝘴𝘦𝘳
│
╰──────────────""")

# ═══════════════════════════════════════════════════════════
# MUTE/BAN COMMANDS
# ═══════════════════════════════════════════════════════════

@dp.message(Command("mute"))
async def cmd_mute(m: Message):
    """Mute user"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    if not await is_admin(m.chat.id, m.from_user.id):
        await m.reply("[ X ] You must be an admin to use this command")
        return
    
    if not m.reply_to_message:
        await m.reply("[ ! ] Reply to a user to mute them\nUsage: /mute [duration in minutes]")
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
    
    # Mute in Telegram
    try:
        await bot.restrict_chat_member(
            m.chat.id,
            target_user.id,
            ChatPermissions(can_send_messages=False),
            until_date=datetime.now() + timedelta(minutes=duration) if duration > 0 else None
        )
    except Exception as e:
        await m.reply(f"[ X ] Failed to mute user: {str(e)[:50]}")
        return
    
    # Store in Redis
    await mute_user(m.chat.id, target_user.id, duration)
    
    duration_text = f"{duration} 𝘮𝘪𝘯𝘶𝘵𝘦𝘴" if duration > 0 else "𝘱𝘦𝘳𝘮𝘢𝘯𝘦𝘯𝘵𝘭𝘺"
    await m.reply(f"""
╭─ 🔇 𝗨𝗦𝗘𝗥 𝗠𝗨𝗧𝗘𝗗
│
│ ▸ 𝘜𝘴𝘦𝘳: {target_user.first_name}
│ ▸ 𝘋𝘶𝘳𝘢𝘵𝘪𝘰𝘯: {duration_text}
│ ▸ 𝘐𝘋: `{target_user.id}`
│
╰──────────────""")

@dp.message(Command("unmute"))
async def cmd_unmute(m: Message):
    """Unmute user"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    if not await is_admin(m.chat.id, m.from_user.id):
        await m.reply("[ X ] You must be an admin to use this command")
        return
    
    if not m.reply_to_message:
        await m.reply("[ ! ] Reply to a user to unmute them")
        return
    
    target_user = m.reply_to_message.from_user
    
    # Unmute in Telegram
    try:
        await bot.restrict_chat_member(
            m.chat.id,
            target_user.id,
            ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False
            )
        )
    except Exception as e:
        await m.reply(f"[ X ] Failed to unmute user: {str(e)[:50]}")
        return
    
    # Remove from Redis
    await unmute_user(m.chat.id, target_user.id)
    
    await m.reply(f"""
╭─ 🔊 𝗨𝗦𝗘𝗥 𝗨𝗡𝗠𝗨𝗧𝗘𝗗
│
│ ▸ 𝘜𝘴𝘦𝘳: {target_user.first_name}
│ ▸ 𝘐𝘋: `{target_user.id}`
│
╰──────────────""")

@dp.message(Command("ban"))
async def cmd_ban(m: Message):
    """Ban user"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    if not await is_admin(m.chat.id, m.from_user.id):
        await m.reply("[ X ] You must be an admin to use this command")
        return
    
    if not m.reply_to_message:
        await m.reply("[ ! ] Reply to a user to ban them")
        return
    
    target_user = m.reply_to_message.from_user
    
    try:
        await bot.ban_chat_member(m.chat.id, target_user.id)
        await m.reply(f"""
╭─ 🚫 𝗨𝗦𝗘𝗥 𝗕𝗔𝗡𝗡𝗘𝗗
│
│ ▸ 𝘜𝘴𝘦𝘳: {target_user.first_name}
│ ▸ 𝘐𝘋: `{target_user.id}`
│
╰──────────────""")
    except Exception as e:
        await m.reply(f"[ X ] Failed to ban user: {str(e)[:50]}")

@dp.message(Command("unban"))
async def cmd_unban(m: Message):
    """Unban user"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    if not await is_admin(m.chat.id, m.from_user.id):
        await m.reply("[ X ] You must be an admin to use this command")
        return
    
    if not m.reply_to_message:
        await m.reply("[ ! ] Reply to a user to unban them")
        return
    
    target_user = m.reply_to_message.from_user
    
    try:
        await bot.unban_chat_member(m.chat.id, target_user.id)
        await m.reply(f"""
╭─ ✅ 𝗨𝗦𝗘𝗥 𝗨𝗡𝗕𝗔𝗡𝗡𝗘𝗗
│
│ ▸ 𝘜𝘴𝘦𝘳: {target_user.first_name}
│ ▸ 𝘐𝘋: `{target_user.id}`
│
╰──────────────""")
    except Exception as e:
        await m.reply(f"[ X ] Failed to unban user: {str(e)[:50]}")

# ═══════════════════════════════════════════════════════════
# FILTER COMMANDS
# ═══════════════════════════════════════════════════════════

@dp.message(Command("filter"))
async def cmd_filter(m: Message):
    """Add word to filter"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    if not await is_admin(m.chat.id, m.from_user.id):
        await m.reply("[ X ] You must be an admin to use this command")
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.reply("[ ! ] Usage: /filter <word>")
        return
    
    word = args[1].strip()
    await add_filter(m.chat.id, word)
    
    await m.reply(f"""
╭─ ✅ 𝗙𝗜𝗟𝗧𝗘𝗥 𝗔𝗗𝗗𝗘𝗗
│
│ ▸ 𝘞𝘰𝘳𝘥: {word}
│ ▸ 𝘔𝘦𝘴𝘴𝘢𝘨𝘦𝘴 𝘤𝘰𝘯𝘵𝘢𝘪𝘯𝘪𝘯𝘨 𝘵𝘩𝘪𝘴 𝘸𝘰𝘳𝘥 𝘸𝘪𝘭𝘭 𝘣𝘦 𝘥𝘦𝘭𝘦𝘵𝘦𝘥
│
╰──────────────""")

@dp.message(Command("unfilter"))
async def cmd_unfilter(m: Message):
    """Remove word from filter"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    if not await is_admin(m.chat.id, m.from_user.id):
        await m.reply("[ X ] You must be an admin to use this command")
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.reply("[ ! ] Usage: /unfilter <word>")
        return
    
    word = args[1].strip()
    await remove_filter(m.chat.id, word)
    
    await m.reply(f"""
╭─ ✅ 𝗙𝗜𝗟𝗧𝗘𝗥 𝗥𝗘𝗠𝗢𝗩𝗘𝗗
│
│ ▸ 𝘞𝘰𝘳𝘥: {word}
│
╰──────────────""")

@dp.message(Command("filters"))
async def cmd_filters(m: Message):
    """List all filters"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    filters = await get_filters(m.chat.id)
    
    if not filters:
        await m.reply("[ ! ] No filters set for this chat")
        return
    
    filter_list = "\n".join([f"│ ▸ {word}" for word in filters])
    
    await m.reply(f"""
╭─ 🛡️ 𝗔𝗖𝗧𝗜𝗩𝗘 𝗙𝗜𝗟𝗧𝗘𝗥𝗦
│
{filter_list}
│
│ 𝘛𝘰𝘵𝘢𝘭: {len(filters)} 𝘧𝘪𝘭𝘵𝘦𝘳𝘴
│
╰──────────────""")

@dp.message(Command("block"))
async def cmd_block(m: Message):
    """Add exact word to blocklist"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    if not await is_admin(m.chat.id, m.from_user.id):
        await m.reply("[ X ] You must be an admin to use this command")
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.reply("[ ! ] Usage: /block <word>")
        return
    
    word = args[1].strip()
    await add_to_blocklist(m.chat.id, word)
    
    await m.reply(f"""
╭─ ✅ 𝗪𝗢𝗥𝗗 𝗕𝗟𝗢𝗖𝗞𝗘𝗗
│
│ ▸ 𝘞𝘰𝘳𝘥: {word}
│ ▸ 𝘖𝘯𝘭𝘺 𝘦𝘹𝘢𝘤𝘵 𝘸𝘰𝘳𝘥 𝘮𝘢𝘵𝘤𝘩𝘦𝘴 𝘸𝘪𝘭𝘭 𝘣𝘦 𝘣𝘭𝘰𝘤𝘬𝘦𝘥
│
╰──────────────""")

@dp.message(Command("unblock"))
async def cmd_unblock(m: Message):
    """Remove word from blocklist"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    if not await is_admin(m.chat.id, m.from_user.id):
        await m.reply("[ X ] You must be an admin to use this command")
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.reply("[ ! ] Usage: /unblock <word>")
        return
    
    word = args[1].strip()
    await remove_from_blocklist(m.chat.id, word)
    
    await m.reply(f"""
╭─ ✅ 𝗪𝗢𝗥𝗗 𝗨𝗡𝗕𝗟𝗢𝗖𝗞𝗘𝗗
│
│ ▸ 𝘞𝘰𝘳𝘥: {word}
│
╰──────────────""")

@dp.message(Command("blocklist"))
async def cmd_blocklist(m: Message):
    """List all blocked words"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    blocklist = await get_blocklist(m.chat.id)
    
    if not blocklist:
        await m.reply("[ ! ] No blocked words for this chat")
        return
    
    block_list = "\n".join([f"│ ▸ {word}" for word in blocklist])
    
    await m.reply(f"""
╭─ 🚫 𝗕𝗟𝗢𝗖𝗞𝗘𝗗 𝗪𝗢𝗥𝗗𝗦
│
{block_list}
│
│ 𝘛𝘰𝘵𝘢𝘭: {len(blocklist)} 𝘣𝘭𝘰𝘤𝘬𝘦𝘥 𝘸𝘰𝘳𝘥𝘴
│
╰──────────────""")

# ═══════════════════════════════════════════════════════════
# WHISPER COMMAND
# ═══════════════════════════════════════════════════════════

@dp.message(Command("whisper"))
async def cmd_whisper(m: Message):
    """Send private message in group"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    if not m.reply_to_message:
        await m.reply("[ ! ] Reply to a user to whisper them\nUsage: /whisper <message>")
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.reply("[ ! ] Usage: /whisper <message>")
        return
    
    target_user = m.reply_to_message.from_user
    message = args[1]
    
    # Delete original command immediately
    try:
        await m.delete()
    except:
        pass
    
    try:
        # Send to target user's DM
        await bot.send_message(
            target_user.id,
            f"""
╭─ 💬 𝗪𝗛𝗜𝗦𝗣𝗘𝗥 𝗠𝗘𝗦𝗦𝗔𝗚𝗘
│
│ 𝘍𝘳𝘰𝘮: {m.from_user.first_name}
│ 𝘊𝘩𝘢𝘵: {m.chat.title}
│
│ 𝘔𝘦𝘴𝘴𝘢𝘨𝘦:
│ {message}
│
╰──────────────"""
        )
        
        logger.info(f"Whisper sent from {m.from_user.id} to {target_user.id} in chat {m.chat.id}")
            
    except Exception as e:
        logger.error(f"Failed to send whisper: {e}")
        # Send error message that auto-deletes
        error_msg = await m.answer(f"[ X ] Failed to send whisper: User may have blocked the bot")
        await asyncio.sleep(5)
        try:
            await error_msg.delete()
        except:
            pass

# ═══════════════════════════════════════════════════════════
# MESSAGE FILTER HANDLER
# ═══════════════════════════════════════════════════════════

@dp.message(F.text & ~F.text.startswith("/"))
async def check_filters_handler(m: Message):
    """Check all messages for filtered/blocked words (skip commands)"""
    if m.chat.type == "private":
        return
    
    # Skip if admin
    if await is_admin(m.chat.id, m.from_user.id):
        return
    
    # Check filters
    is_filtered, reason = await check_message_filters(m.chat.id, m.text)
    
    if is_filtered:
        try:
            await m.delete()
            warning = await m.answer(f"[ ! ] Message deleted: {reason}")
            await asyncio.sleep(5)
            try:
                await warning.delete()
            except:
                pass
        except Exception as e:
            logger.error(f"Failed to delete filtered message: {e}")

def register_admin_handlers():
    """Register all admin handlers - called from main"""
    logger.info("Admin handlers registered")
