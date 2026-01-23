# ===================== IMPORTS =====================
import asyncio
import logging
import os
import re
import glob
import secrets
import subprocess
import sqlite3
import time
from contextlib import closing
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatType
from aiogram.filters import BaseFilter, Command
from aiogram.types import (
    Message,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.exceptions import TelegramForbiddenError
from yt_dlp import YoutubeDL

# ===================== CONFIG =====================
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
SELECTION_TIMEOUT = 15

# ===================== BOT =====================
logging.basicConfig(level=logging.INFO)
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

# ===================== DATABASE =====================
def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with closing(db()) as conn, conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS authorized_chats (
            chat_id INTEGER PRIMARY KEY,
            authorized_at INTEGER,
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

# ===================== DB HELPERS =====================
def authorize_chat(chat_id: int, days: int):
    now = int(time.time())
    exp = now + days * 86400
    with closing(db()) as conn, conn:
        conn.execute(
            "INSERT OR REPLACE INTO authorized_chats VALUES (?,?,?)",
            (chat_id, now, exp),
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

# ===================== FORCE JOIN =====================
async def ensure_joined(user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(FORCE_JOIN_CHANNEL, user_id)
        return m.status in ("member", "administrator", "creator")
    except:
        return False

# ===================== UTIL =====================
def human_time(seconds: int) -> str:
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return f"{d}d {h}h {m}m {s}s"

def mention(user) -> str:
    if user.username:
        return f"@{user.username}"
    return f'<a href="tg://user?id={user.id}">{user.first_name}</a>'

def random_prefix():
    return f"vid_{secrets.token_hex(6)}"

def find_file(prefix: str):
    files = glob.glob(f"{prefix}.*")
    return files[0] if files else None

# ===================== DOMAINS =====================
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

# ===================== FILTER =====================
class HasURL(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(re.search(r"https?://", message.text or ""))

# ===================== METADATA =====================
def get_duration(url: str):
    with YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("duration")

# ===================== DOWNLOAD =====================
def download_video(url: str):
    prefix = random_prefix()
    with YoutubeDL({
        "outtmpl": f"{prefix}.%(ext)s",
        "quiet": True,
        "merge_output_format": "mp4",
        "format": "bestvideo+bestaudio/best",
    }) as ydl:
        ydl.download([url])
    return find_file(prefix)

# ===================== SEGMENT =====================
def segment_video(path: str, bitrate: str):
    base = path.replace(".mp4", "")
    out = f"{base}_part%03d.mp4"

    cmd = [
        "ffmpeg", "-y", "-i", path,
        "-vf",
        "scale=iw*min(1280/iw\\,720/ih):ih*min(1280/iw\\,720/ih),"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-r", "30",
        "-g", "60",
        "-keyint_min", "60",
        "-sc_threshold", "0",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "23",
        "-maxrate", bitrate,
        "-bufsize", "2.5M",
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-movflags", "+faststart",
        "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_TIME})",
        "-f", "segment",
        "-segment_time", str(SEGMENT_TIME),
        "-reset_timestamps", "1",
        out,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sorted(glob.glob(f"{base}_part*.mp4"))

# ===================== PREMIUM UI TEXTS =====================
UI_START = (
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "Downloader Bot\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "• High-quality media downloads\n"
    "• Premium group access\n"
    "• Privacy-first processing\n"
    "• Clean, automated handling\n\n"
    "› Use /help to view commands\n"
    "› Premium features require authorization\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━"
)

UI_HELP = (
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "Help & Commands\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "▸ /start\n  Open main menu\n\n"
    "▸ /status\n  View chat status\n\n"
    "▸ /help_admin\n  Admin controls\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━"
)

# ===================== START =====================
@dp.message(Command("start"))
async def start_cmd(m: Message):
    if not await ensure_joined(m.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Join Channel", url="https://t.me/downloaderbackup")
        ]])
        await m.reply(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Access Restricted\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "This service requires channel membership.\n\n"
            "› Join the channel to continue\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━",
            reply_markup=kb,
        )
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Features", callback_data="features"),
            InlineKeyboardButton(text="Status", callback_data="status"),
        ],
        [InlineKeyboardButton(text="Contact Admin", url="https://t.me/downloaderbackup")],
    ])
    await m.reply(UI_START, reply_markup=kb)

# ===================== HELP =====================
@dp.message(Command("help"))
async def help_cmd(m: Message):
    await m.reply(UI_HELP)

# ===================== ADMIN HELP =====================
@dp.message(Command("help_admin"))
async def help_admin(m: Message):
    await m.reply(
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Admin Control Panel\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "▸ /auth <days>\n"
        "▸ /unauth\n"
        "▸ /extend <days>\n"
        "▸ /autodelete on|off\n"
        "▸ /status\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

# ===================== STATUS =====================
@dp.message(Command("status"))
async def status_cmd(m: Message):
    exp = get_auth_expiry(m.chat.id)
    if not exp:
        await m.reply(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Chat Status\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⟡ Authorization : Inactive\n"
            "⟡ Access        : Restricted\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        return

    await m.reply(
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Chat Status\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⟡ Authorization : Active\n"
        f"⟡ Expiry        : {human_time(exp - int(time.time()))}\n"
        f"⟡ Auto-Delete   : {'ON' if get_autodelete(m.chat.id) else 'OFF'}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

# ===================== AUTH COMMANDS =====================
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
        f"⟡ Duration : {days} days\n\n"
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
        "⟡ Access : Removed\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

@dp.message(Command("extend"))
async def extend_cmd(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    days = int(m.text.split()[1])
    exp = get_auth_expiry(m.chat.id)
    if not exp:
        await m.reply("Chat not authorized.")
        return
    authorize_chat(m.chat.id, days + (exp - int(time.time())) // 86400)
    await m.reply(
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Subscription Extended\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⟡ Added Time : {days} days\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

@dp.message(Command("autodelete"))
async def autodel_cmd(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    arg = m.text.split()[1].lower()
    set_autodelete(m.chat.id, arg == "on")
    await m.reply(
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Group Settings\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⟡ Auto-Delete : {arg.upper()}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

# ===================== URL HANDLER (MAIN LOGIC) =====================
@dp.message(HasURL())
async def url_handler(m: Message):
    chat = m.chat
    user = m.from_user
    urls = re.findall(r"https?://[^\s]+", m.text or "")

    for url in urls:
        # PUBLIC
        if is_public(url):
            try:
                await m.delete()
            except:
                pass
            path = download_video(url)
            if not path:
                return
            await bot.send_video(
                chat_id=chat.id,
                video=FSInputFile(path),
                supports_streaming=True,
            )
            os.unlink(path)
            return

        # PRIVATE (XHAMSTER)
        if is_private(url):
            if chat.type == ChatType.PRIVATE:
                allowed, reset = check_rate_limit(user.id)
                if not allowed:
                    await m.reply(
                        f"Rate limit reached. Try again in {reset//60} minutes."
                    )
                    return
            else:
                if not get_auth_expiry(chat.id):
                    return

            duration = get_duration(url)
            if not duration or duration > MAX_HARD:
                await m.reply("Video too long.")
                return

            quality = DEFAULT_QUALITY
            if duration > MAX_SOFT:
                quality = "540p"

            path = download_video(url)
            parts = segment_video(path, QUALITY_PRESETS[quality])

            mention_text = mention(user)
            sent_ids = []

            for i, part in enumerate(parts, 1):
                msg = await bot.send_video(
                    chat_id=chat.id,
                    video=FSInputFile(part),
                    caption=f"Part {i}/{len(parts)} ({quality})\nRequested by {mention_text}",
                    reply_to_message_id=m.message_id if chat.type != ChatType.PRIVATE else None,
                )
                sent_ids.append(msg.message_id)

            if get_autodelete(chat.id):
                await asyncio.sleep(30)
                for mid in sent_ids:
                    try:
                        await bot.delete_message(chat.id, mid)
                    except:
                        pass
                await bot.send_message(chat.id, "History cleared.")

            for p in parts:
                os.unlink(p)
            os.unlink(path)
            return

# ===================== MAIN =====================
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
