# Management Commands for Telegram Bot
# Add these to main.py after the help command

# ═══════════════════════════════════════════════════════════
# MANAGEMENT COMMANDS
# ═══════════════════════════════════════════════════════════

@dp.message(Command("id"))
async def cmd_id(m: Message):
    """Get user ID"""
    if m.reply_to_message:
        user = m.reply_to_message.from_user
        await m.reply(f"""
╔══════════════════════════╗
║      USER ID INFO        ║
╚══════════════════════════╝

├─ Name: {user.first_name}
├─ Username: @{user.username if user.username else 'None'}
└─ ID: {user.id}""")
    else:
        await m.reply(f"""
╔══════════════════════════╗
║      YOUR ID INFO        ║
╚══════════════════════════╝

├─ Name: {m.from_user.first_name}
├─ Username: @{m.from_user.username if m.from_user.username else 'None'}
└─ ID: {m.from_user.id}""")

@dp.message(Command("chatid"))
async def cmd_chatid(m: Message):
    """Get chat ID"""
    await m.reply(f"""
╔══════════════════════════╗
║      CHAT ID INFO        ║
╚══════════════════════════╝

├─ Chat Name: {m.chat.title if m.chat.title else 'Private Chat'}
├─ Chat Type: {m.chat.type}
└─ Chat ID: {m.chat.id}""")

@dp.message(Command("myinfo"))
async def cmd_myinfo(m: Message):
    """Get detailed user info"""
    user = m.from_user
    await m.reply(f"""
╔══════════════════════════╗
║    YOUR INFORMATION      ║
╚══════════════════════════╝

USER DETAILS
├─ First Name: {user.first_name}
├─ Last Name: {user.last_name if user.last_name else 'None'}
├─ Username: @{user.username if user.username else 'None'}
├─ ID: {user.id}
└─ Language: {user.language_code if user.language_code else 'Unknown'}

CHAT DETAILS
├─ Chat Name: {m.chat.title if m.chat.title else 'Private Chat'}
├─ Chat Type: {m.chat.type}
└─ Chat ID: {m.chat.id}""")

# ═══════════════════════════════════════════════════════════
# ADMIN MANAGEMENT
# ═══════════════════════════════════════════════════════════

@dp.message(Command("promote"))
async def cmd_promote(m: Message):
    """Promote user to admin"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    # Check if sender is admin
    try:
        member = await bot.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["creator", "administrator"]:
            await m.reply("[ X ] You must be an admin to use this command")
            return
    except:
        await m.reply("[ X ] Failed to check admin status")
        return
    
    if not m.reply_to_message:
        await m.reply("[ ! ] Reply to a user to promote them")
        return
    
    target_user = m.reply_to_message.from_user
    await add_admin(m.chat.id, target_user.id)
    
    await m.reply(f"""
╔══════════════════════════╗
║    USER PROMOTED         ║
╚══════════════════════════╝

{target_user.first_name} is now an admin!
User ID: {target_user.id}""")

@dp.message(Command("demote"))
async def cmd_demote(m: Message):
    """Demote admin"""
    if m.chat.type == "private":
        await m.reply("[ ! ] This command only works in groups")
        return
    
    # Check if sender is admin
    try:
        member = await bot.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["creator", "administrator"]:
            await m.reply("[ X ] You must be an admin to use this command")
            return
    except:
        await m.reply("[ X ] Failed to check admin status")
        return
    
    if not m.reply_to_message:
        await m.reply("[ ! ] Reply to a user to demote them")
        return
    
    target_user = m.reply_to_message.from_user
    await remove_admin(m.chat.id, target_user.id)
    
    await m.reply(f"""
╔══════════════════════════╗
║    USER DEMOTED          ║
╚══════════════════════════╝

{target_user.first_name} is no longer an admin
User ID: {target_user.id}""")

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
    
    duration_text = f"{duration} minutes" if duration > 0 else "permanently"
    await m.reply(f"""
╔══════════════════════════╗
║    USER MUTED            ║
╚══════════════════════════╝

User: {target_user.first_name}
Duration: {duration_text}
User ID: {target_user.id}""")

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
╔══════════════════════════╗
║    USER UNMUTED          ║
╚══════════════════════════╝

User: {target_user.first_name}
User ID: {target_user.id}""")

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
╔══════════════════════════╗
║    USER BANNED           ║
╚══════════════════════════╝

User: {target_user.first_name}
User ID: {target_user.id}""")
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
╔══════════════════════════╗
║    USER UNBANNED         ║
╚══════════════════════════╝

User: {target_user.first_name}
User ID: {target_user.id}""")
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
╔══════════════════════════╗
║    FILTER ADDED          ║
╚══════════════════════════╝

Word: {word}
Messages containing this word will be deleted""")

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
╔══════════════════════════╗
║    FILTER REMOVED        ║
╚══════════════════════════╝

Word: {word}""")

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
    
    filter_list = "\n".join([f"├─ {word}" for word in filters[:-1]])
    filter_list += f"\n└─ {filters[-1]}" if filters else ""
    
    await m.reply(f"""
╔══════════════════════════╗
║    ACTIVE FILTERS        ║
╚══════════════════════════╝

{filter_list}

Total: {len(filters)} filters""")

# ═══════════════════════════════════════════════════════════
# BLOCKLIST COMMANDS
# ═══════════════════════════════════════════════════════════

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
╔══════════════════════════╗
║    WORD BLOCKED          ║
╚══════════════════════════╝

Word: {word}
Only exact word matches will be blocked""")

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
╔══════════════════════════╗
║    WORD UNBLOCKED        ║
╚══════════════════════════╝

Word: {word}""")

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
    
    block_list = "\n".join([f"├─ {word}" for word in blocklist[:-1]])
    block_list += f"\n└─ {blocklist[-1]}" if blocklist else ""
    
    await m.reply(f"""
╔══════════════════════════╗
║    BLOCKED WORDS         ║
╚══════════════════════════╝

{block_list}

Total: {len(blocklist)} blocked words""")

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
    
    try:
        # Send to target user's DM
        await bot.send_message(
            target_user.id,
            f"""
╔══════════════════════════╗
║    WHISPER MESSAGE       ║
╚══════════════════════════╝

From: {m.from_user.first_name}
Chat: {m.chat.title}

Message:
{message}"""
        )
        
        # Delete original command
        try:
            await m.delete()
        except:
            pass
        
        # Send confirmation (will auto-delete)
        conf = await m.answer(f"[ ✓ ] Whisper sent to {target_user.first_name}")
        await asyncio.sleep(3)
        try:
            await conf.delete()
        except:
            pass
            
    except Exception as e:
        await m.reply(f"[ X ] Failed to send whisper: {str(e)[:50]}")

# ═══════════════════════════════════════════════════════════
# MESSAGE FILTER HANDLER
# ═══════════════════════════════════════════════════════════

@dp.message(F.text)
async def check_filters(m: Message):
    """Check all messages for filtered/blocked words"""
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
        except:
            pass
