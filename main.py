# =========================
# main.py — FINAL HARDENED
# =========================

import asyncio
import logging
import os
import re
import sqlite3
import subprocess
import time
import secrets
import glob
from contextlib import closing
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, BaseFilter
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatType
from yt_dlp import YoutubeDL

# ======================================================
# CONFIG (HARDCODED)
# ======================================================
BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"
OWNER_ID = 7363967303
REQUIRED_CHANNEL = "@downloaderbackup"
DB_PATH = "bot.db"

AUTO_DELETE_SECONDS = 30
SEGMENT_TIME = 300

MAX_SOFT = 30 * 60
MAX_HARD = 45 * 60

IG_LIMIT_PER_HOUR = 40
XH_LIMIT_PER_HOUR = 6

QUALITY_BITRATE = {
    "1080p": "2.0M",
    "720p": "1.2M",
    "540p": "1.0M",
    "480p": "0.8M",
}
DEFAULT_QUALITY = "720p"

IG_PRESET = "veryfast"
IG_CRF_PRIMARY = 24
IG_CRF_FALLBACK = 26
IG_MAXRATE = "4.0M"
IG_BUFSIZE = "8M"
IG_AUDIO = "128k"

# ======================================================
# LOGGING
# ======================================================
logging.basicConfig(level=logging.WARNING)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)

bot = Bot(BOT_TOKEN, parse_mode=None)
dp = Dispatcher()

# ======================================================
# PREMIUM UI
# ======================================================
DIV = "━━━━━━━━━━━━━━━━━━━━━━"

UI = {
    "ACCESS_GRANTED": f"""{DIV}
ACCESS GRANTED
{DIV}

Welcome to the private service.

High-speed processing
Quality-controlled downloads
Session-based cleanup enabled

{DIV}
""",
    "ACCESS_DENIED": f"""{DIV}
ACCESS DENIED
{DIV}

Required channel membership
has not been detected.

This session remains locked.

{DIV}
""",
    "START": f"""{DIV}
Downloader Bot
{DIV}

• High-quality media downloads
• Premium group access control
• Private processing pipeline
• Automatic cleanup & protection

› Use /help to view commands

{DIV}
""",
    "HELP": f"""{DIV}
Help & Commands
{DIV}

• Send a supported link to download
• Instagram: fast & optimized
• XHamster: duration-aware chunks

Commands:
• /status
• /help

{DIV}
""",
    "PROCESS_1": f"""{DIV}
PROCESSING REQUEST
{DIV}

• Source detected
""",
    "PROCESS_2": f"""{DIV}
PROCESSING REQUEST
{DIV}

• Downloading media
""",
    "PROCESS_3": f"""{DIV}
PROCESSING REQUEST
{DIV}

• Optimizing quality
""",
    "STATUS_ACTIVE": f"""{DIV}
Chat Status
{DIV}

⟡ Authorization : Active
⟡ Expiry        : {{remaining}}
⟡ Auto-Delete   : {{autodel}}

{DIV}
""",
    "STATUS_INACTIVE": f"""{DIV}
Chat Status
{DIV}

⟡ Authorization : Inactive
⟡ Access        : Restricted

{DIV}
""",
    "AUTH_UPDATED": f"""{DIV}
Authorization Updated
{DIV}

⟡ Chat Status : Authorized
⟡ Duration    : {{days}} days

{DIV}
""",
    "UNAUTH": f"""{DIV}
Authorization Revoked
{DIV}

⟡ Chat Status : Disabled
⟡ Access      : Removed

{DIV}
""",
    "HELP_ADMIN": f"""{DIV}
Admin Control Panel
{DIV}

▸ /auth <days>
▸ /extend <days>
▸ /unauth
▸ /autodelete on|off
▸ /settings
▸ /status

{DIV}
""",
    "SETTINGS": f"""{DIV}
Group Settings
{DIV}

⟡ Authorization : {{auth}}
⟡ Auto-Delete   : {{autodel}}
⟡ Expiry        : {{remaining}}

{DIV}
""",
    "ERROR": f"""{DIV}
REQUEST FAILED
{DIV}

{{reason}}

{DIV}
""",
    "RATE_LIMIT": f"""{DIV}
RATE LIMIT
{DIV}

Too many requests.
Please try again later.

{DIV}
""",
    "SESSION_LOG": f"""{DIV}
SESSION LOG
{DIV}

Media removed successfully.

Requested by : {{user}}
Source       : {{source}}
Duration     : {{duration}}
Chat Type    : {{chat_type}}

Status       : Completed

{DIV}
"""
}

# ======================================================
# DATABASE
# ======================================================
def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with closing(db()) as conn, conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            authorized INTEGER DEFAULT 0,
            expires_at INTEGER DEFAULT 0,
            auto_delete INTEGER DEFAULT 1
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS limits (
            user_id INTEGER,
            source TEXT,
            ts INTEGER,
            cnt INTEGER,
            PRIMARY KEY (user_id, source)
        )""")

def authorize(chat_id, days):
    exp = int(time.time()) + days * 86400
    with closing(db()) as conn, conn:
        conn.execute(
            "INSERT OR REPLACE INTO chats(chat_id,authorized,expires_at,auto_delete) "
            "VALUES (?,?,?,COALESCE((SELECT auto_delete FROM chats WHERE chat_id=?),1))",
            (chat_id, 1, exp, chat_id)
        )

def extend(chat_id, days):
    with closing(db()) as conn, conn:
        row = conn.execute("SELECT expires_at FROM chats WHERE chat_id=?", (chat_id,)).fetchone()
        now = int(time.time())
        new_exp = (row[0] if row and row[0] > now else now) + days * 86400
        conn.execute("UPDATE chats SET expires_at=?, authorized=1 WHERE chat_id=?", (new_exp, chat_id))

def unauthorize(chat_id):
    with closing(db()) as conn, conn:
        conn.execute("UPDATE chats SET authorized=0 WHERE chat_id=?", (chat_id,))

def get_chat(chat_id):
    with closing(db()) as conn:
        return conn.execute(
            "SELECT authorized, expires_at, auto_delete FROM chats WHERE chat_id=?",
            (chat_id,)
        ).fetchone()

def is_authorized(chat_id):
    row = get_chat(chat_id)
    if not row:
        return False
    auth, exp, _ = row
    return bool(auth and exp > int(time.time()))

def autodel(chat_id):
    row = get_chat(chat_id)
    return bool(row and row[2])

def set_autodel(chat_id, v):
    with closing(db()) as conn, conn:
        conn.execute("UPDATE chats SET auto_delete=? WHERE chat_id=?", (1 if v else 0, chat_id))

def rate_ok(user_id, source, limit):
    now = int(time.time())
    with closing(db()) as conn, conn:
        row = conn.execute(
            "SELECT ts, cnt FROM limits WHERE user_id=? AND source=?",
            (user_id, source)
        ).fetchone()
        if not row or now - row[0] >= 3600:
            conn.execute(
                "INSERT OR REPLACE INTO limits VALUES (?,?,?,?)",
                (user_id, source, now, 1)
            )
            return True
        ts, cnt = row
        if cnt >= limit:
            return False
        conn.execute(
            "UPDATE limits SET cnt=? WHERE user_id=? AND source=?",
            (cnt + 1, user_id, source)
        )
        return True

# ======================================================
# HELPERS
# ======================================================
class HasURL(BaseFilter):
    async def __call__(self, m: Message):
        return bool(re.search(r"https?://", m.text or ""))

def mention(user):
    return f"@{user.username}" if user and user.username else (user.first_name if user else "Unknown")

def human(sec):
    sec = max(0, sec)
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return f"{d}d {h}h {m}m {s}s"

def domain(url):
    return urlparse(url).netloc.lower()

async def check_channel(user_id):
    try:
        m = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return m.status in ("member", "administrator", "creator")
    except:
        return False

# Per-chat processing lock
CHAT_LOCKS = {}

async def acquire_lock(chat_id):
    lock = CHAT_LOCKS.setdefault(chat_id, asyncio.Lock())
    if lock.locked():
        return False
    await lock.acquire()
    return True

def release_lock(chat_id):
    lock = CHAT_LOCKS.get(chat_id)
    if lock and lock.locked():
        lock.release()

# ======================================================
# DOWNLOAD UTILS
# ======================================================
def ytdlp_info(url):
    with YoutubeDL({"quiet": True, "skip_download": True}) as y:
        return y.extract_info(url, download=False)

def ytdlp_download(url, outtmpl):
    with YoutubeDL({
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "format": "bestvideo+bestaudio/best",
        "quiet": True,
        "noplaylist": True
    }) as y:
        y.download([url])

def ffmpeg_reencode(src, dst, crf):
    subprocess.run([
        "ffmpeg","-y","-i",src,
        "-c:v","libx264",
        "-preset",IG_PRESET,
        "-crf",str(crf),
        "-maxrate",IG_MAXRATE,
        "-bufsize",IG_BUFSIZE,
        "-pix_fmt","yuv420p",
        "-movflags","+faststart",
        "-c:a","aac","-b:a",IG_AUDIO,
        dst
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def segment_xh(src, br):
    base = src.replace(".mp4","")
    out = f"{base}_%03d.mp4"
    subprocess.run([
        "ffmpeg","-y","-i",src,
        "-c:v","libx264","-crf","23",
        "-maxrate",br,"-bufsize","2M",
        "-c:a","aac","-b:a","128k",
        "-f","segment","-segment_time",str(SEGMENT_TIME),
        "-reset_timestamps","1",
        out
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sorted(glob.glob(f"{base}_*.mp4"))

# ======================================================
# COMMANDS
# ======================================================
@dp.message(Command("start"))
async def start(m: Message):
    if not await check_channel(m.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}")],
            [InlineKeyboardButton(text="I Have Joined", callback_data="recheck")]
        ])
        await m.reply(UI["ACCESS_DENIED"], reply_markup=kb)
        return
    await m.reply(UI["START"])

@dp.message(Command("help"))
async def help_cmd(m: Message):
    await m.reply(UI["HELP"])

@dp.callback_query(lambda c: c.data == "recheck")
async def recheck(cb):
    if await check_channel(cb.from_user.id):
        await cb.message.edit_text(UI["ACCESS_GRANTED"])
    else:
        await cb.answer("Not verified yet", show_alert=True)

@dp.message(Command("status"))
async def status(m: Message):
    row = get_chat(m.chat.id)
    if not row or not row[0]:
        await m.reply(UI["STATUS_INACTIVE"])
        return
    _, exp, ad = row
    await m.reply(UI["STATUS_ACTIVE"].format(
        remaining=human(exp - int(time.time())),
        autodel="ON" if ad else "OFF"
    ))

@dp.message(Command("auth"))
async def auth(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    days = int(m.text.split()[1])
    authorize(m.chat.id, days)
    await m.reply(UI["AUTH_UPDATED"].format(days=days))

@dp.message(Command("extend"))
async def extend_cmd(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    days = int(m.text.split()[1])
    extend(m.chat.id, days)
    await m.reply(UI["AUTH_UPDATED"].format(days=days))

@dp.message(Command("unauth"))
async def unauth(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    unauthorize(m.chat.id)
    await m.reply(UI["UNAUTH"])

@dp.message(Command("autodelete"))
async def ad(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    set_autodel(m.chat.id, m.text.split()[1].lower() == "on")
    await m.reply("Updated")

@dp.message(Command("help_admin"))
async def help_admin(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    await m.reply(UI["HELP_ADMIN"])

@dp.message(Command("settings"))
async def settings(m: Message):
    if m.from_user.id != OWNER_ID:
        return
    row = get_chat(m.chat.id)
    if not row:
        await m.reply(UI["STATUS_INACTIVE"])
        return
    auth, exp, ad = row
    await m.reply(UI["SETTINGS"].format(
        auth="Active" if auth else "Inactive",
        autodel="ON" if ad else "OFF",
        remaining=human(exp - int(time.time())) if auth else "—"
    ))

# ======================================================
# URL HANDLER (LAST)
# ======================================================
@dp.message(HasURL())
async def handle(m: Message):
    if not await acquire_lock(m.chat.id):
        await m.reply(UI["ERROR"].format(reason="Another request is in progress. Please wait."))
        return

    urls = re.findall(r"https?://[^\s]+", m.text or "")
    for url in urls:
        d = domain(url)

        try:
            # ---------- INSTAGRAM ----------
            if "instagram.com" in d or "instagr.am" in d:
                if m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and not is_authorized(m.chat.id):
                    await m.reply(UI["ACCESS_DENIED"])
                    return
                if not rate_ok(m.from_user.id, "instagram", IG_LIMIT_PER_HOUR):
                    await m.reply(UI["RATE_LIMIT"])
                    return

                proc = await m.reply(UI["PROCESS_1"])
                await proc.edit_text(UI["PROCESS_2"])

                info = ytdlp_info(url)
                duration = info.get("duration", 0)

                base = f"ig_{secrets.token_hex(6)}"
                raw = f"{base}_raw.mp4"
                out = f"{base}.mp4"

                ytdlp_download(url, raw)
                await proc.edit_text(UI["PROCESS_3"])
                ffmpeg_reencode(raw, out, IG_CRF_PRIMARY)

                if os.path.getsize(out) > 45 * 1024 * 1024:
                    ffmpeg_reencode(raw, out, IG_CRF_FALLBACK)

                await proc.delete()
                sent = await m.reply_video(
                    FSInputFile(out),
                    caption=f"Requested by {mention(m.from_user)}",
                    supports_streaming=True
                )

                if m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and autodel(m.chat.id):
                    await asyncio.sleep(AUTO_DELETE_SECONDS)
                    for mid in (sent.message_id, m.message_id):
                        try:
                            await bot.delete_message(m.chat.id, mid)
                        except:
                            pass
                    await m.reply(UI["SESSION_LOG"].format(
                        user=mention(m.from_user),
                        source="Instagram",
                        duration=time.strftime("%M:%S", time.gmtime(duration)),
                        chat_type="Group"
                    ))

                for f in (raw, out):
                    if os.path.exists(f):
                        os.remove(f)
                return

            # ---------- XHAMSTER ----------
            if "xhamster" in d:
                if m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and not is_authorized(m.chat.id):
                    await m.reply(UI["ACCESS_DENIED"])
                    return
                if not rate_ok(m.from_user.id, "xhamster", XH_LIMIT_PER_HOUR):
                    await m.reply(UI["RATE_LIMIT"])
                    return

                proc = await m.reply(UI["PROCESS_1"])
                await proc.edit_text(UI["PROCESS_2"])

                info = ytdlp_info(url)
                duration = info.get("duration", 0)
                if duration > MAX_HARD:
                    await proc.delete()
                    await m.reply(UI["ERROR"].format(
                        reason=f"Video duration {int(duration//60)} min exceeds max {int(MAX_HARD//60)} min."
                    ))
                    return

                quality = DEFAULT_QUALITY if duration <= MAX_SOFT else "540p"
                base = f"xh_{secrets.token_hex(6)}"
                raw = f"{base}.mp4"
                ytdlp_download(url, raw)

                await proc.edit_text(UI["PROCESS_3"])
                parts = segment_xh(raw, QUALITY_BITRATE[quality])
                await proc.delete()

                sent_ids = []
                for i, p in enumerate(parts, 1):
                    msg = await m.reply_video(
                        FSInputFile(p),
                        caption=f"Part {i}/{len(parts)} · {quality}\nRequested by {mention(m.from_user)}",
                        supports_streaming=True
                    )
                    sent_ids.append(msg.message_id)
                    os.remove(p)

                if m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and autodel(m.chat.id):
                    await asyncio.sleep(AUTO_DELETE_SECONDS)
                    for mid in sent_ids + [m.message_id]:
                        try:
                            await bot.delete_message(m.chat.id, mid)
                        except:
                            pass
                    await m.reply(UI["SESSION_LOG"].format(
                        user=mention(m.from_user),
                        source="XHamster",
                        duration=time.strftime("%M:%S", time.gmtime(duration)),
                        chat_type="Group"
                    ))

                if os.path.exists(raw):
                    os.remove(raw)
                return

            # ---------- GENERIC ----------
            proc = await m.reply(UI["PROCESS_1"])
            await proc.edit_text(UI["PROCESS_2"])
            base = f"gen_{secrets.token_hex(6)}"
            raw = f"{base}.mp4"
            ytdlp_download(url, raw)
            await proc.delete()
            sent = await m.reply_video(FSInputFile(raw), caption=f"Requested by {mention(m.from_user)}")
            if m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and autodel(m.chat.id):
                await asyncio.sleep(AUTO_DELETE_SECONDS)
                for mid in (sent.message_id, m.message_id):
                    try:
                        await bot.delete_message(m.chat.id, mid)
                    except:
                        pass
                await m.reply(UI["SESSION_LOG"].format(
                    user=mention(m.from_user),
                    source="Generic",
                    duration="—",
                    chat_type="Group"
                ))
            os.remove(raw)
            return

        finally:
            release_lock(m.chat.id)

# ======================================================
# MAIN
# ======================================================
async def main():
    init_db()
    # cleanup leftovers
    for f in glob.glob("ig_*.mp4") + glob.glob("xh_*.mp4") + glob.glob("gen_*.mp4"):
        try:
            os.remove(f)
        except:
            pass
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
