import asyncio, os, re, subprocess, tempfile, time, logging, random, glob, json
from pathlib import Path
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, FSInputFile, ChatPermissions
from yt_dlp import YoutubeDL
from upstash_redis import Redis

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("NAGU")

# ═══════════════════════════════════════════════════════════
# ENVIRONMENT VARIABLES - ALL SECRETS FROM ENV
# ═══════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
REDIS_URL = os.getenv("REDIS_URL", "")
REDIS_TOKEN = os.getenv("REDIS_TOKEN", "")

# Proxies from environment (comma-separated)
PROXIES_STR = os.getenv("PROXIES", "")
PROXIES = [p.strip() for p in PROXIES_STR.split(",") if p.strip()] if PROXIES_STR else []

# Cookie files and folders
IG_COOKIES = "cookies_instagram.txt"
YT_COOKIES_FOLDER = "yt cookies"
YT_MUSIC_COOKIES_FOLDER = "yt music cookies"

# Stickers
IG_STICKER = os.getenv("IG_STICKER", "CAACAgIAAxkBAAEadEdpekZa1-2qYm-1a3dX0JmM_Z9uDgAC4wwAAjAT0Euml6TE9QhYWzgE")
YT_STICKER = os.getenv("YT_STICKER", "CAACAgIAAxkBAAEaedlpez9LOhwF-tARQsD1V9jzU8iw1gACQjcAAgQyMEixyZ896jTkCDgE")
PIN_STICKER = os.getenv("PIN_STICKER", "CAACAgIAAxkBAAEaegZpe0KJMDIkiCbudZrXhJDwBXYHqgACExIAAq3mUUhZ4G5Cm78l2DgE")
MUSIC_STICKER = os.getenv("MUSIC_STICKER", "CAACAgIAAxkBAAEaegZpe0KJMDIkiCbudZrXhJDwBXYHqgACExIAAq3mUUhZ4G5Cm78l2DgE")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]

def pick_proxy(): return random.choice(PROXIES) if PROXIES else None
def pick_ua(): return random.choice(USER_AGENTS)

# ═══════════════════════════════════════════════════════════
# REDIS DATABASE CONNECTION
# ═══════════════════════════════════════════════════════════

try:
    redis = Redis(url=REDIS_URL, token=REDIS_TOKEN)
    logger.info("Redis connected successfully")
except Exception as e:
    logger.error(f"Redis connection failed: {e}")
    redis = None

# Cookie rotation system
def get_random_cookie(folder):
    """Get random cookie file from folder"""
    if not os.path.exists(folder):
        return None
    cookies = glob.glob(f"{folder}/*.txt")
    if not cookies:
        return None
    return random.choice(cookies)

def resolve_pin(url):
    if "pin.it/" in url:
        return subprocess.getoutput(f"curl -Ls -o /dev/null -w '%{{url_effective}}' {url}")
    return url

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
semaphore = asyncio.Semaphore(16)
MUSIC_SEMAPHORE = asyncio.Semaphore(2)

LINK_RE = re.compile(r"https?://\S+")

# ═══════════════════════════════════════════════════════════
# REDIS HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════

def get_admin_key(chat_id): return f"admins:{chat_id}"
def get_mute_key(chat_id, user_id): return f"mute:{chat_id}:{user_id}"
def get_filter_key(chat_id): return f"filters:{chat_id}"
def get_blocklist_key(chat_id): return f"blocklist:{chat_id}"

async def is_admin(chat_id, user_id):
    """Check if user is admin"""
    if not redis: return False
    try:
        admins = redis.smembers(get_admin_key(chat_id))
        return str(user_id) in [str(a) for a in admins]
    except:
        return False

async def add_admin(chat_id, user_id):
    """Add user as admin"""
    if redis:
        redis.sadd(get_admin_key(chat_id), str(user_id))

async def remove_admin(chat_id, user_id):
    """Remove user from admins"""
    if redis:
        redis.srem(get_admin_key(chat_id), str(user_id))

async def is_muted(chat_id, user_id):
    """Check if user is muted"""
    if not redis: return False
    try:
        mute_until = redis.get(get_mute_key(chat_id, user_id))
        if not mute_until: return False
        if datetime.now().timestamp() > float(mute_until):
            redis.delete(get_mute_key(chat_id, user_id))
            return False
        return True
    except:
        return False

async def mute_user(chat_id, user_id, duration_minutes=0):
    """Mute user for duration (0 = permanent)"""
    if not redis: return
    if duration_minutes == 0:
        redis.set(get_mute_key(chat_id, user_id), "permanent")
    else:
        until = (datetime.now() + timedelta(minutes=duration_minutes)).timestamp()
        redis.set(get_mute_key(chat_id, user_id), str(until))

async def unmute_user(chat_id, user_id):
    """Unmute user"""
    if redis:
        redis.delete(get_mute_key(chat_id, user_id))

async def add_filter(chat_id, word):
    """Add word to filter list"""
    if redis:
        redis.sadd(get_filter_key(chat_id), word.lower())

async def remove_filter(chat_id, word):
    """Remove word from filter list"""
    if redis:
        redis.srem(get_filter_key(chat_id), word.lower())

async def get_filters(chat_id):
    """Get all filtered words"""
    if not redis: return []
    try:
        return list(redis.smembers(get_filter_key(chat_id)))
    except:
        return []

async def add_to_blocklist(chat_id, word):
    """Add exact word to blocklist"""
    if redis:
        redis.sadd(get_blocklist_key(chat_id), word.lower())

async def remove_from_blocklist(chat_id, word):
    """Remove word from blocklist"""
    if redis:
        redis.srem(get_blocklist_key(chat_id), word.lower())

async def get_blocklist(chat_id):
    """Get all blocked words"""
    if not redis: return []
    try:
        return list(redis.smembers(get_blocklist_key(chat_id)))
    except:
        return []

async def check_message_filters(chat_id, text):
    """Check if message contains filtered/blocked words"""
    if not text: return False, None
    text_lower = text.lower()
    
    # Check blocklist (exact word match)
    blocklist = await get_blocklist(chat_id)
    words = text_lower.split()
    for blocked in blocklist:
        if blocked in words:
            return True, f"Blocked word: {blocked}"
    
    # Check filters (substring match)
    filters = await get_filters(chat_id)
    for filtered in filters:
        if filtered in text_lower:
            return True, f"Filtered word: {filtered}"
    
    return False, None

# ═══════════════════════════════════════════════════════════
# MINIMALIST PREMIUM UI
# ═══════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def start(m: Message):
    username = f"@{m.from_user.username}" if m.from_user.username else "No Username"
    
    caption = f"""
╔══════════════════════════╗
║   NAGU DOWNLOADER BOT    ║
╚══════════════════════════╝

USER INFORMATION
├─ ID: {m.from_user.id}
├─ Username: {username}
└─ Name: {m.from_user.first_name}

COMMANDS
├─ /help - View all features
├─ /mp3 - Download music
└─ Send any link to download

═══════════════════════════
Owner: @bhosadih
═══════════════════════════"""
    
    # Try to send with picture
    picture_path = Path("assets/picture.png")
    if picture_path.exists():
        try:
            await m.reply_photo(FSInputFile(picture_path), caption=caption)
            return
        except:
            pass
    
    # Fallback to text only
    await m.reply(caption, quote=True)

@dp.message(F.text == "/help")
async def help_command(m: Message):
    await m.reply("""
╔══════════════════════════╗
║    BOT HELP & FEATURES   ║
╚══════════════════════════╝

VIDEO DOWNLOAD
├─ Instagram: Posts, Reels, Stories
├─ YouTube: Videos, Shorts, Streams
└─ Pinterest: Video Pins
   >> Just send the link!

MUSIC DOWNLOAD
├─ /mp3 [song name]
│  └─ Search & download any song
└─ Spotify Playlists
   └─ Send Spotify URL

INFO COMMANDS
├─ /id - Get user ID
├─ /chatid - Get chat ID
└─ /myinfo - Your full info

ADMIN COMMANDS
├─ /promote - Make user admin
├─ /demote - Remove admin
├─ /mute [minutes] - Mute user
├─ /unmute - Unmute user
├─ /ban - Ban user
└─ /unban - Unban user

FILTER COMMANDS
├─ /filter <word> - Filter word
├─ /unfilter <word> - Remove filter
├─ /filters - List filters
├─ /block <word> - Block exact word
├─ /unblock <word> - Unblock word
└─ /blocklist - List blocked

OTHER
└─ /whisper <msg> - Private message

═══════════════════════════
Owner: @bhosadih
═══════════════════════════""")

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

@dp.message(F.text & ~F.text.startswith("/") & ~F.text.regexp(LINK_RE))
async def check_filters(m: Message):
    """Check all messages for filtered/blocked words (skip commands and links)"""
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

def mention(u):
    return f'<a href="tg://user?id={u.id}">{u.first_name}</a>'

def caption(m, elapsed):
    return (
        f"₪ 𝐔𝐬𝐞𝐫: {mention(m.from_user)}\n"
        f"₪ 𝐓𝐢𝐦𝐞: {elapsed:.2f}s"
    )

def run(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ═══════════════════════════════════════════════════════════
# INSTAGRAM - ULTRA FAST MP4
# ═══════════════════════════════════════════════════════════

async def ig_download(url, out, use_cookies=False):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "best[height<=720][ext=mp4]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(out),
        "proxy": pick_proxy(),
        "http_headers": {"User-Agent": pick_ua()},
        "concurrent_fragment_downloads": 20,
        "http_chunk_size": 10485760,
    }
    
    if use_cookies and os.path.exists(IG_COOKIES):
        opts["cookiefile"] = IG_COOKIES
        logger.info("Using Instagram cookies (fallback)")
    
    await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))

def ig_optimize(src, out):
    """OLD FAST PIPELINE - instant remux if small, fast VP9 if large"""
    size_mb = src.stat().st_size / 1024 / 1024
    logger.info(f"IG: {size_mb:.2f} MB")
    
    if size_mb <= 18:
        # PATH 1: INSTANT REMUX (NO RE-ENCODE)
        logger.info("IG: Fast copy (<=18MB)")
        run(["ffmpeg", "-y", "-i", str(src), "-c", "copy", str(out)])
    else:
        # PATH 2: FAST HIGH COMPRESSION
        logger.info("IG: Fast VP9 compression (>18MB)")
        run([
            "ffmpeg", "-y", "-i", str(src),
            "-vf", "scale=720:-2",
            "-c:v", "libvpx-vp9", "-crf", "26", "-b:v", "0",
            "-cpu-used", "8", "-row-mt", "1",
            "-pix_fmt", "yuv420p",
            "-c:a", "libopus", "-b:a", "48k",
            "-movflags", "+faststart",
            str(out)
        ])

async def handle_instagram(m, url):
    logger.info(f"IG: {url}")
    s = await bot.send_sticker(m.chat.id, IG_STICKER)
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            raw = t / "ig.mp4"
            final = t / "igf.mp4"

            # Try without cookies first
            try:
                await ig_download(url, raw, use_cookies=False)
            except:
                logger.info("IG: Retrying with cookies")
                await ig_download(url, raw, use_cookies=True)

            # OLD FAST PIPELINE
            await asyncio.to_thread(ig_optimize, raw, final)

            elapsed = time.perf_counter() - start
            try:
                await bot.delete_message(m.chat.id, s.message_id)
            except:
                pass

            sent = await bot.send_video(
                m.chat.id, FSInputFile(final),
                caption=caption(m, elapsed),
                parse_mode="HTML",
                supports_streaming=True
            )

            if m.chat.type != "private":
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            
            logger.info(f"IG: Done in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"IG: {e}")
        try:
            await bot.delete_message(m.chat.id, s.message_id)
        except:
            pass
        await m.answer(f"❌ 𝐈𝐧𝐬𝐭𝐚𝐠𝐫𝐚𝐦 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}")

# ═══════════════════════════════════════════════════════════
# YOUTUBE - FAST VP9 WITH BITRATE
# ═══════════════════════════════════════════════════════════

async def handle_youtube(m, url):
    logger.info(f"YT: {url}")
    s = await bot.send_sticker(m.chat.id, YT_STICKER)
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            raw = t / "yt.mp4"
            final = t / "ytf.mp4"

            opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "best[height<=720][ext=mp4]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best",
                "merge_output_format": "mp4",
                "outtmpl": str(raw),
                "proxy": pick_proxy(),
                "http_headers": {
                    "User-Agent": pick_ua(),
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "DNT": "1",
                },
                "socket_timeout": 30,
                "retries": 3,
                "concurrent_fragment_downloads": 20,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "web"],
                        "player_skip": ["webpage", "configs"],
                    }
                },
            }
            
            # Try without cookies first, then with rotation
            try:
                await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))
            except:
                cookie_file = get_random_cookie(YT_COOKIES_FOLDER)
                if cookie_file:
                    logger.info(f"YT: Using cookie {cookie_file}")
                    opts["cookiefile"] = cookie_file
                    await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))
                else:
                    raise

            # VP9 with bitrate (up to 12MB)
            await asyncio.to_thread(lambda: run([
                "ffmpeg", "-y", "-i", str(raw),
                "-vf", "scale=720:-2",
                "-c:v", "libvpx-vp9", "-b:v", "1200k", "-maxrate", "1500k", "-bufsize", "2400k",
                "-cpu-used", "4", "-row-mt", "1",
                "-pix_fmt", "yuv420p",
                "-c:a", "libopus", "-b:a", "128k",
                "-movflags", "+faststart",
                str(final)
            ]))

            elapsed = time.perf_counter() - start
            try:
                await bot.delete_message(m.chat.id, s.message_id)
            except:
                pass

            sent = await bot.send_video(
                m.chat.id, FSInputFile(final),
                caption=caption(m, elapsed),
                parse_mode="HTML",
                supports_streaming=True
            )

            if m.chat.type != "private":
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            
            logger.info(f"YT: Done in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"YT: {e}")
        try:
            await bot.delete_message(m.chat.id, s.message_id)
        except:
            pass
        await m.answer(f"❌ 𝐘𝐨𝐮𝐓𝐮𝐛𝐞 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}")

# ═══════════════════════════════════════════════════════════
# PINTEREST - PERFECT (UNCHANGED)
# ═══════════════════════════════════════════════════════════

async def handle_pinterest(m, url):
    url = resolve_pin(url)
    logger.info(f"PIN: {url}")

    s = await bot.send_sticker(m.chat.id, PIN_STICKER)
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            raw = t / "pin.mp4"
            final = t / "pinf.mp4"

            opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "best/bestvideo+bestaudio",
                "merge_output_format": "mp4",
                "outtmpl": str(raw),
                "proxy": pick_proxy(),
                "http_headers": {"User-Agent": pick_ua()},
                "concurrent_fragment_downloads": 20,
            }

            await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))

            # Fast copy with MP4 optimization
            await asyncio.to_thread(lambda: run([
                "ffmpeg", "-y", "-i", str(raw),
                "-c:v", "copy", "-c:a", "copy",
                "-movflags", "+faststart",
                str(final)
            ]))

            elapsed = time.perf_counter() - start
            try:
                await bot.delete_message(m.chat.id, s.message_id)
            except:
                pass

            sent = await bot.send_video(
                m.chat.id, FSInputFile(final),
                caption=caption(m, elapsed),
                parse_mode="HTML",
                supports_streaming=True
            )

            if m.chat.type != "private":
                await bot.pin_chat_message(m.chat.id, sent.message_id)
            
            logger.info(f"PIN: Done in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"PIN: {e}")
        try:
            await bot.delete_message(m.chat.id, s.message_id)
        except:
            pass
        await m.answer(f"❌ 𝐏𝐢𝐧𝐭𝐞𝐫𝐞𝐬𝐭 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}")

# ═══════════════════════════════════════════════════════════
# SPOTIFY PLAYLIST DOWNLOADER (IMPROVED WITH YT-DLP)
# ═══════════════════════════════════════════════════════════

async def download_single_track(track_info, tmp_dir, cookie_file, retry_count=0):
    """Download a single track with proper metadata and thumbnail"""
    try:
        query = f"{track_info['artist']} {track_info['title']}"
        logger.info(f"Downloading: {query}")
        
        # Add delay before download to avoid rate limiting (3-5 seconds)
        await asyncio.sleep(random.uniform(3.0, 5.0))
        
        opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
            "outtmpl": str(tmp_dir / "%(title)s.%(ext)s"),
            "proxy": pick_proxy(),
            "http_headers": {
                "User-Agent": pick_ua(),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            },
            "default_search": "ytsearch1",
            "writethumbnail": True,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                },
                {
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": False,
                },
                {
                    "key": "FFmpegMetadata",
                    "add_metadata": True,
                }
            ],
            "postprocessor_args": [
                "-ar", "44100",
                "-ac", "2",
                "-b:a", "192k",
            ],
        }
        
        if cookie_file:
            opts["cookiefile"] = cookie_file
        
        with YoutubeDL(opts) as ydl:
            info = await asyncio.to_thread(lambda: ydl.extract_info(f"ytsearch1:{query}", download=True))
            
            # Find the downloaded MP3
            for f in tmp_dir.iterdir():
                if f.suffix == ".mp3" and f.stat().st_size > 0:
                    return {
                        'file': f,
                        'title': track_info['title'],
                        'artist': track_info['artist'],
                        'size_mb': f.stat().st_size / 1024 / 1024
                    }
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to download {track_info['title']}: {e}")
        
        # Retry with different cookie if first attempt fails
        if retry_count < 1:
            logger.info(f"Retrying {track_info['title']} with different cookie...")
            await asyncio.sleep(5)  # Wait before retry
            new_cookie = get_random_cookie(YT_MUSIC_COOKIES_FOLDER)
            return await download_single_track(track_info, tmp_dir, new_cookie, retry_count + 1)
        
        return None

def create_progress_bar(current, total, length=10):
    """Create a text-based progress bar"""
    filled = int(length * current / total)
    bar = '█' * filled + '░' * (length - filled)
    percent = int(100 * current / total)
    return f"[{bar}] {percent}%"

async def download_spotify_playlist(m, url):
    """Download Spotify playlist using spotdl directly"""
    logger.info(f"SPOTIFY: {url}")
    
    # Check if Spotify credentials are set
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        await m.answer("[ X ] Spotify API not configured")
        return
    
    # Phase 1: Processing
    status_msg = await m.answer("""
╔══════════════════════════╗
║   SPOTIFY PLAYLIST       ║
╚══════════════════════════╝

PHASE 1/3: Processing
[░░░░░░░░░░] 0%

Status: Initializing...""")
    start = time.perf_counter()
    
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            
            # Phase 2: Downloading
            await status_msg.edit_text("""
╔══════════════════════════╗
║   SPOTIFY PLAYLIST       ║
╚══════════════════════════╝

PHASE 2/3: Downloading
[███░░░░░░░] 33%

Status: Downloading songs...""")
            
            # Use spotdl to download entire playlist
            cmd = [
                "spotdl",
                "download",
                url,
                "--client-id", SPOTIFY_CLIENT_ID,
                "--client-secret", SPOTIFY_CLIENT_SECRET,
                "--output", str(tmp),
                "--format", "mp3",
                "--bitrate", "192k",
                "--threads", "1",
                "--print-errors",
            ]
            
            logger.info(f"Running spotdl download...")
            result = await asyncio.to_thread(
                lambda: subprocess.run(cmd, capture_output=True, text=True)
            )
            
            if result.returncode != 0:
                logger.error(f"spotdl failed: {result.stderr}")
                await status_msg.edit_text(f"[ X ] Spotify Failed\n{result.stderr[:100]}")
                return
            
            # Find all downloaded MP3 files
            mp3_files = list(tmp.glob("*.mp3"))
            
            if not mp3_files:
                await status_msg.edit_text("[ X ] No songs downloaded")
                return
            
            total = len(mp3_files)
            
            # Phase 3: Sending to DM
            await status_msg.edit_text(f"""
╔══════════════════════════╗
║   SPOTIFY PLAYLIST       ║
╚══════════════════════════╝

PHASE 3/3: Sending to DM
[██████░░░░] 66%

Status: Sending {total} songs...""")
            
            sent = 0
            failed = 0
            
            # Send each song to DM (without caption)
            for i, mp3 in enumerate(mp3_files, 1):
                try:
                    # Extract artist and title from filename
                    filename = mp3.stem
                    if ' - ' in filename:
                        artist, title = filename.split(' - ', 1)
                    else:
                        artist = "Unknown Artist"
                        title = filename
                    
                    file_size = mp3.stat().st_size / 1024 / 1024
                    
                    # Send without caption
                    await bot.send_audio(
                        m.from_user.id,
                        FSInputFile(mp3),
                        title=title,
                        performer=artist
                    )
                    sent += 1
                    logger.info(f"DM: {title} by {artist} ({file_size:.1f}MB)")
                    
                    # Update progress every 5 songs
                    if i % 5 == 0 or i == total:
                        progress_bar = create_progress_bar(sent, total)
                        try:
                            await status_msg.edit_text(f"""
╔══════════════════════════╗
║   SPOTIFY PLAYLIST       ║
╚══════════════════════════╝

PHASE 3/3: Sending to DM
{progress_bar}

Status: Sent {sent}/{total} songs""")
                        except:
                            pass
                    
                    # Small delay between sends
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Failed to send {mp3.name}: {e}")
                    failed += 1
        
            elapsed = time.perf_counter() - start
            
            # Final status in group
            await status_msg.edit_text(f"""
╔══════════════════════════╗
║   PLAYLIST COMPLETED     ║
╚══════════════════════════╝

{mention(m.from_user)}

SUMMARY
├─ Total Songs: {total}
├─ Sent to DM: {sent}
├─ Failed: {failed}
└─ Time: {elapsed:.1f}s

All songs sent to your DM!""", parse_mode="HTML")
            
            logger.info(f"SPOTIFY: {sent} songs in {elapsed:.2f}s")
        
    except Exception as e:
        logger.error(f"SPOTIFY: {e}")
        try:
            await status_msg.edit_text(f"[ X ] Spotify Failed\n{str(e)[:100]}")
        except:
            await m.answer(f"[ X ] Spotify Failed\n{str(e)[:100]}")

# ═══════════════════════════════════════════════════════════
# MP3 SEARCH COMMAND (WITH COOKIE ROTATION)
# ═══════════════════════════════════════════════════════════

async def search_and_download_song(m, query):
    """Search and download single song with proper metadata and thumbnail"""
    async with MUSIC_SEMAPHORE:
        logger.info(f"MP3: {query}")
        s = await bot.send_sticker(m.chat.id, MUSIC_STICKER)
        start = time.perf_counter()

        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                
                opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "format": "bestaudio/best",
                    "outtmpl": str(tmp / "%(title)s.%(ext)s"),
                    "proxy": pick_proxy(),
                    "http_headers": {
                        "User-Agent": pick_ua(),
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "DNT": "1",
                    },
                    "default_search": "ytsearch1",
                    "writethumbnail": True,
                    "socket_timeout": 30,
                    "retries": 3,
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        },
                        {
                            "key": "EmbedThumbnail",
                            "already_have_thumbnail": False,
                        },
                        {
                            "key": "FFmpegMetadata",
                            "add_metadata": True,
                        }
                    ],
                    "postprocessor_args": [
                        "-ar", "44100",
                        "-ac", "2",
                        "-b:a", "192k",
                    ],
                }
                
                # Use random cookie from yt_music_cookies folder
                cookie_file = get_random_cookie(YT_MUSIC_COOKIES_FOLDER)
                if cookie_file:
                    opts["cookiefile"] = cookie_file
                    logger.info(f"MP3: Using cookie {cookie_file}")
                
                # Search and download
                with YoutubeDL(opts) as ydl:
                    info = await asyncio.to_thread(lambda: ydl.extract_info(f"ytsearch1:{query}", download=True))
                
                # Find MP3
                mp3 = None
                for f in tmp.iterdir():
                    if f.suffix == ".mp3":
                        mp3 = f
                        break
                
                if not mp3:
                    await bot.delete_message(m.chat.id, s.message_id)
                    await m.answer("❌ 𝐒𝐨𝐧𝐠 𝐧𝐨𝐭 𝐟𝐨𝐮𝐧𝐝")
                    return
                
                # Extract metadata
                entry = info['entries'][0] if 'entries' in info else info
                title = entry.get('title', mp3.stem)
                artist = entry.get('artist') or entry.get('uploader', 'Unknown Artist')
                file_size = mp3.stat().st_size / 1024 / 1024
                
                elapsed = time.perf_counter() - start
                await bot.delete_message(m.chat.id, s.message_id)
                
                # Send to chat
                await bot.send_audio(
                    m.chat.id,
                    FSInputFile(mp3),
                    caption=(
                        f"𝐌𝐏𝟑 𝐃𝐎𝐖𝐍𝐋𝐎𝐀𝐃 ★\n"
                        f"- - - - - - - - - - - - - - - - - - - - - - - - - - - -\n"
                        f"🎵 {title}\n"
                        f"🎤 {artist}\n"
                        f"💾 {file_size:.1f}MB\n"
                        f"₪ 𝐔𝐬𝐞𝐫: {mention(m.from_user)}\n"
                        f"₪ 𝐓𝐢𝐦𝐞: {elapsed:.2f}s"
                    ),
                    parse_mode="HTML",
                    title=title,
                    performer=artist
                )
                
                logger.info(f"MP3: {title} by {artist} ({file_size:.1f}MB) in {elapsed:.2f}s")
                
        except Exception as e:
            logger.error(f"MP3: {e}")
            try:
                await bot.delete_message(m.chat.id, s.message_id)
            except:
                pass
            await m.answer(f"❌ 𝐌𝐏𝟑 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}")

@dp.message(Command("mp3"))
async def mp3_command(m: Message):
    query = m.text.replace("/mp3", "").strip()
    if not query:
        await m.answer("𝐔𝐬𝐚𝐠𝐞: /mp3 song name")
        return
    await search_and_download_song(m, query)

# ═══════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════

@dp.message(F.text.regexp(LINK_RE))
async def handle(m: Message):
    url = m.text.strip()

    # Delete user's link after 5 seconds
    async def delete_link_later():
        await asyncio.sleep(5)
        try:
            await m.delete()
            logger.info("Deleted user's link after 5s")
        except:
            pass
    
    asyncio.create_task(delete_link_later())

    async with semaphore:
        try:
            if "instagram.com" in url.lower():
                await handle_instagram(m, url)
            elif "youtube.com" in url.lower() or "youtu.be" in url.lower():
                await handle_youtube(m, url)
            elif "pinterest.com" in url.lower() or "pin.it" in url.lower():
                await handle_pinterest(m, url)
            elif "spotify.com" in url.lower():
                await download_spotify_playlist(m, url)
            else:
                await m.answer("❌ 𝐔𝐧𝐬𝐮𝐩𝐩𝐨𝐫𝐭𝐞𝐝 𝐏𝐥𝐚𝐭𝐟𝐨𝐫𝐦")
        except Exception as e:
            logger.error(f"Error: {e}")
            await m.answer(f"❌ 𝐄𝐫𝐫𝐨𝐫\n{str(e)[:100]}")

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

async def main():
    logger.info("NAGU DOWNLOADER BOT - STARTING")
    logger.info(f"Semaphore: 16 concurrent downloads")
    logger.info(f"Proxies: {len(PROXIES)}")
    
    # Check cookie folders
    if os.path.exists(YT_COOKIES_FOLDER):
        yt_cookies = len(glob.glob(f"{YT_COOKIES_FOLDER}/*.txt"))
        logger.info(f"YT cookies: {yt_cookies} files")
    
    if os.path.exists(YT_MUSIC_COOKIES_FOLDER):
        music_cookies = len(glob.glob(f"{YT_MUSIC_COOKIES_FOLDER}/*.txt"))
        logger.info(f"YT Music cookies: {music_cookies} files")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
