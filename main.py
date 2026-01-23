import asyncio
import logging
import os
import re
import glob
import secrets
import sqlite3
import subprocess
import time
from contextlib import closing
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatType
from aiogram.filters import Command, BaseFilter
from aiogram.types import (
    Message,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from yt_dlp import YoutubeDL

# ==================================================
# CONFIG
# ==================================================
BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"
OWNER_ID = 7363967303
FORCE_JOIN_CHANNEL = "@downloaderbackup"
DB_PATH = "bot.db"

PM_LIMIT = 6  # per hour

MAX_SOFT = 30 * 60
MAX_HARD = 45 * 60
SEGMENT_TIME = 300
AUDIO_BITRATE = "128k"

QUALITY_PRESETS = {
    "1080p": "2.0M",
    "720p": "1.2M",
    "480p": "0.8M",
    "540p": "1.0M",
}

DEFAULT_QUALITY = "720p"

# ==================================================
# BOT
# ==================================================
logging.basicConfig(level=logging.INFO)
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

# ==================================================
# DATABASE
# ==================================================
def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with closing(db()) as conn, conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS authorized_chats (
            chat_id INTEGER PRIMARY KEY,
            expires_at INTEGER
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS gc_settings (
            chat_id INTEGER PRIMARY KEY,
            auto_delete INTEGER DEFAULT 1
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            user_id INTEGER PRIMARY KEY,
            window_start INTEGER,
            count INTEGER
        )""")

# ==================================================
# PREMIUM UI CONSTANTS (CANONICAL)
# ==================================================
UI_ACCESS_RESTRICTED = """━━━━━━━━━━━━━━━━━━━━━━
ACCESS RESTRICTED
━━━━━━━━━━━━━━━━━━━━━━

This service operates under
controlled access.

Channel membership is mandatory
to proceed further.

Failure to comply will result in
continued access denial.

━━━━━━━━━━━━━━━━━━━━━━
"""

UI_ACCESS_DENIED = """━━━━━━━━━━━━━━━━━━━━━━
ACCESS DENIED
━━━━━━━━━━━━━━━━━━━━━━

Verification could not be completed.

Required channel membership
has not been detected.

This session remains locked.
Repeated attempts may result in
permanent access suspension.

━━━━━━━━━━━━━━━━━━━━━━
"""

UI_ACCESS_GRANTED = """━━━━━━━━━━━━━━━━━━━━━━
ACCESS GRANTED
━━━━━━━━━━━━━━━━━━━━━━

Welcome to the private service.

High-speed processing
Quality-controlled downloads
Session-based cleanup enabled

This environment is monitored.

━━━━━━━━━━━━━━━━━━━━━━
"""

UI_START_MENU = """━━━━━━━━━━━━━━━━━━━━━━
Downloader Bot
━━━━━━━━━━━━━━━━━━━━━━

• High-quality media downloads
• Premium group access control
• Private processing pipeline
• Automatic cleanup & protection

› Use /help to view commands
› Unauthorized usage is restricted

━━━━━━━━━━━━━━━━━━━━━━
"""

UI_SERVICE_OVERVIEW = """━━━━━━━━━━━━━━━━━━━━━━
SERVICE OVERVIEW
━━━━━━━━━━━━━━━━━━━━━━

• Multi-source media processing
• Adaptive quality control
• Chunk-safe delivery system
• Automatic session cleanup
• Group & private support

Usage is logged per session.

━━━━━━━━━━━━━━━━━━━━━━
"""

UI_NOTICE_DELETE = """━━━━━━━━━━━━━━━━━━━━━━
NOTICE
━━━━━━━━━━━━━━━━━━━━━━

This media will be removed
automatically in 30 seconds.

━━━━━━━━━━━━━━━━━━━━━━
"""

UI_SESSION_CLEARED = """━━━━━━━━━━━━━━━━━━━━━━
SESSION CLEARED
━━━━━━━━━━━━━━━━━━━━━━

Your history was cleared.

━━━━━━━━━━━━━━━━━━━━━━
"""

UI_ADMIN_PANEL = """━━━━━━━━━━━━━━━━━━━━━━
Admin Control Panel
━━━━━━━━━━━━━━━━━━━━━━

▸ /auth <days>
  Authorize this chat

▸ /unauth
  Revoke chat access

▸ /extend <days>
  Extend subscription

▸ /autodelete on|off
  Toggle auto-delete

▸ /status
  View chat status

━━━━━━━━━━━━━━━━━━━━━━
"""

UI_HELP = """━━━━━━━━━━━━━━━━━━━━━━
Help & Commands
━━━━━━━━━━━━━━━━━━━━━━

▸ /start
  Open main menu

▸ /status
  View chat authorization & expiry

▸ /help_admin
  Admin-only controls

━━━━━━━━━━━━━━━━━━━━━━
"""

# ==================================================
# DB HELPERS
# ==================================================
def authorize_chat(chat_id: int, days: int):
    exp = int(time.time()) + days * 86400
    with closing(db()) as conn, conn:
        conn.execute(
            "INSERT OR REPLACE INTO authorized_chats VALUES (?,?)",
            (chat_id, exp),
        )
        conn.execute(
            "INSERT OR IGNORE INTO gc_settings(chat_id) VALUES (?)",
            (chat_id,),
        )

def unauthorize_chat(chat_id: int):
    with closing(db()) as conn, conn:
        conn.execute("DELETE FROM authorized_chats WHERE chat_id=?", (chat_id,))

def get_auth_expiry(chat_id: int):
    with closing(db()) as conn:
        row = conn.execute(
            "SELECT expires_at FROM authorized_chats WHERE chat_id=?",
            (chat_id,),
        ).fetchone()
        if not row:
            return None
        if row[0] < time.time():
            unauthorize_chat(chat_id)
            return None
        return row[0]

def get_autodelete(chat_id: int) -> bool:
    with closing(db()) as conn:
        row = conn.execute(
            "SELECT auto_delete FROM gc_settings WHERE chat_id=?",
            (chat_id,),
        ).fetchone()
        return bool(row[0]) if row else True

def set_autodelete(chat_id: int, value: bool):
    with closing(db()) as conn, conn:
        conn.execute(
            "UPDATE gc_settings SET auto_delete=? WHERE chat_id=?",
            (1 if value else 0, chat_id),
        )

def check_rate_limit(user_id: int):
    now = int(time.time())
    with closing(db()) as conn, conn:
        row = conn.execute(
            "SELECT window_start, count FROM rate_limits WHERE user_id=?",
            (user_id,),
        ).fetchone()

        if not row:
            conn.execute(
                "INSERT INTO rate_limits VALUES (?,?,?)",
                (user_id, now, 1),
            )
            return True, 3600

        start, count = row
        if now - start >= 3600:
            conn.execute(
                "UPDATE rate_limits SET window_start=?, count=1 WHERE user_id=?",
                (now, user_id),
            )
            return True, 3600

        if count >= PM_LIMIT:
            return False, 3600 - (now - start)

        conn.execute(
            "UPDATE rate_limits SET count=count+1 WHERE user_id=?",
            (user_id,),
        )
        return True, 3600 - (now - start)

# ==================================================
# UTIL
# ==================================================
def human_time(seconds: int) -> str:
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return f"{d} days, {h} hours, {m} minutes, {s} seconds"

def mention(user) -> str:
    if user.username:
        return f"@{user.username}"
    return f'<a href="tg://user?id={user.id}">{user.first_name}</a>'

def random_prefix():
    return f"vid_{secrets.token_hex(6)}"

# ==================================================
# DOMAINS (EXTENSIBLE)
# ==================================================
PUBLIC_DOMAINS = [
    "instagram.com",
    "facebook.com",
    "fb.watch",
    "x.com",
    "twitter.com",
]

PRIVATE_DOMAINS = [
    "xhamster.com",
    "xhamster.xxx",
    "xhamster44.desi",
]

def domain(url: str) -> str:
    return urlparse(url).netloc.lower()

def is_public(url: str) -> bool:
    return any(d in domain(url) for d in PUBLIC_DOMAINS)

def is_private(url: str) -> bool:
    return any(d in domain(url) for d in PRIVATE_DOMAINS)

# ==================================================
# FILTER
# ==================================================
class HasURL(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(re.search(r"https?://", message.text or ""))

# ==================================================
# FORCE JOIN
# ==================================================
async def ensure_joined(user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(FORCE_JOIN_CHANNEL, user_id)
        return m.status in ("member", "administrator", "creator")
    except:
        return False

# ==================================================
# DOWNLOAD PIPELINE
# ==================================================
def get_duration(url: str):
    with YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("duration")

def download_video(url: str):
    prefix = random_prefix()
    with YoutubeDL({
        "outtmpl": f"{prefix}.%(ext)s",
        "quiet": True,
        "merge_output_format": "mp4",
        "format": "bestvideo+bestaudio/best",
    }) as ydl:
        ydl.download([url])
    files = glob.glob(f"{prefix}.*")
    return files[0] if files else None

def segment_video(path: str, bitrate: str):
    base = path.replace(".mp4", "")
    out = f"{base}_part%03d.mp4"

    cmd = [
        "ffmpeg", "-y", "-i", path,
        "-r", "30",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "23",
        "-maxrate", bitrate,
        "-bufsize", "2.5M",
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-movflags", "+faststart",
        "-f", "segment",
        "-segment_time", str(SEGMENT_TIME),
        "-reset_timestamps", "1",
        out,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sorted(glob.glob(f"{base}_part*.mp4"))

# ==================================================
# START / VERIFY
# ==================================================
@dp.message(Command("start"))
async def start_cmd(m: Message):
    if not await ensure_joined(m.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Join Channel", url="https://t.me/downloaderbackup")],
            [InlineKeyboardButton(text="I Have Joined", callback_data="verify_join")],
        ])
        await m.reply(UI_ACCESS_RESTRICTED, reply_markup=kb)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Help", callback_data="help"),
            InlineKeyboardButton(text="Status", callback_data="status"),
        ],
    ])
    await m.reply(UI_START_MENU, reply_markup=kb)

@dp.callback_query(F.data == "verify_join")
async def verify_join(cb: CallbackQuery):
    await cb.answer()
    await asyncio.sleep(2)

    if not await ensure_joined(cb.from_user.id):
        await cb.message.edit_text(
            UI_ACCESS_DENIED,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Join Channel", url="https://t.me/downloaderbackup")]
            ]),
        )
        return

    await cb.message.edit_text(UI_ACCESS_GRANTED)

# ==================================================
# HELP / STATUS / ADMIN
# ==================================================
@dp.callback_query(F.data == "help")
async def help_cb(cb: CallbackQuery):
    await cb.answer()
    await cb.message.reply(UI_HELP)

@dp.callback_query(F.data == "status")
async def status_cb(cb: CallbackQuery):
    await cb.answer()
    exp = get_auth_expiry(cb.message.chat.id)
    if not exp:
        await cb.message.reply(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Chat Status\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⟡ Authorization : Inactive\n"
            "⟡ Access        : Restricted\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        return

    await cb.message.reply(
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Chat Status\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⟡ Authorization : Active\n"
        f"⟡ Expiry        : {human_time(exp - int(time.time()))}\n"
        f"⟡ Auto-Delete   : {'ON' if get_autodelete(cb.message.chat.id) else 'OFF'}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

@dp.message(Command("help_admin"))
async def help_admin(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    await m.reply(UI_ADMIN_PANEL)

@dp.message(Command("auth"))
async def auth_cmd(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    days = int(m.text.split()[1]) if len(m.text.split()) > 1 else 30
    authorize_chat(m.chat.id, days)
    await m.reply(
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Authorization Updated\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⟡ Chat Status : Authorized\n"
        f"⟡ Duration    : {days} days\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

@dp.message(Command("unauth"))
async def unauth_cmd(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    unauthorize_chat(m.chat.id)
    await m.reply(
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Authorization Revoked\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "⟡ Chat Status : Disabled\n"
        "⟡ Access      : Removed\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

@dp.message(Command("extend"))
async def extend_cmd(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    days = int(m.text.split()[1])
    exp = get_auth_expiry(m.chat.id)
    if not exp:
        return
    new_exp = exp + days * 86400
    with closing(db()) as conn, conn:
        conn.execute(
            "UPDATE authorized_chats SET expires_at=? WHERE chat_id=?",
            (new_exp, m.chat.id),
        )
    await m.reply(
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Subscription Extended\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⟡ Added Time : {days} days\n"
        f"⟡ Remaining : {human_time(new_exp - int(time.time()))}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

@dp.message(Command("autodelete"))
async def autodelete_cmd(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    arg = m.text.split()[1].lower()
    set_autodelete(m.chat.id, arg == "on")
    state = "ON" if get_autodelete(m.chat.id) else "OFF"
    await m.reply(
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Group Settings\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⟡ Auto-Delete : {state}\n"
        f"⟡ Status      : Updated\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

# ==================================================
# URL HANDLER
# ==================================================
@dp.message(HasURL())
async def url_handler(m: Message):
    urls = re.findall(r"https?://[^\s]+", m.text or "")
    for url in urls:

        # PUBLIC
        if is_public(url):
            path = download_video(url)
            if path:
                await m.reply_video(FSInputFile(path))
                os.unlink(path)
            return

        # PRIVATE
        if is_private(url):
            if m.chat.type != ChatType.PRIVATE and not get_auth_expiry(m.chat.id):
                return

            if m.chat.type == ChatType.PRIVATE:
                allowed, reset = check_rate_limit(m.from_user.id)
                if not allowed:
                    await m.reply(
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        "Rate Limit\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"Try again in {reset // 60} minutes.\n\n"
                        "━━━━━━━━━━━━━━━━━━━━━━"
                    )
                    return

            duration = get_duration(url)
            if not duration or duration > MAX_HARD:
                await m.reply(
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "Rejected\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "Video duration exceeds limit.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━"
                )
                return

            quality = DEFAULT_QUALITY
            if duration > MAX_SOFT:
                quality = "540p"

            path = download_video(url)
            parts = segment_video(path, QUALITY_PRESETS[quality])

            sent_ids = []
            for i, part in enumerate(parts, 1):
                msg = await m.reply_video(
                    FSInputFile(part),
                    caption=f"Part {i}/{len(parts)} ({quality})\nRequested by {mention(m.from_user)}",
                )
                sent_ids.append(msg.message_id)
                os.unlink(part)

            if get_autodelete(m.chat.id):
                await m.reply(UI_NOTICE_DELETE)
                await asyncio.sleep(30)
                for mid in sent_ids:
                    try:
                        await bot.delete_message(m.chat.id, mid)
                    except:
                        pass
                await m.reply(UI_SESSION_CLEARED)

            os.unlink(path)
            return

# ==================================================
# MAIN
# ==================================================
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
