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

from aiogram import Bot, Dispatcher
from aiogram.enums import ChatType
from aiogram.filters import Command, BaseFilter
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from yt_dlp import YoutubeDL

# ===================== CONFIG =====================
BOT_TOKEN = "8585605391:AAF6FWxlLSNvDLHqt0Al5-iy7BH7Iu7S640"
OWNER_ID = 7363967303
FORCE_JOIN_CHANNEL = "@downloaderbackup"
DB_PATH = "bot.db"

PM_LIMIT = 6
AUTO_DELETE_SECONDS = 30
SEGMENT_TIME = 300

MAX_SOFT = 30 * 60
MAX_HARD = 45 * 60

QUALITY_BITRATE = {
    "1080p": "2.0M",
    "720p": "1.2M",
    "540p": "1.0M",
    "480p": "0.8M",
}

DEFAULT_QUALITY = "720p"

# ===================== LOGGING =====================
logging.basicConfig(level=logging.WARNING)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===================== UI =====================
DIV = "━━━━━━━━━━━━━━━━━━━━━━"

UI_PROCESS_1 = f"""{DIV}
PROCESSING REQUEST
{DIV}

• Source detected
"""

UI_PROCESS_2 = f"""{DIV}
PROCESSING REQUEST
{DIV}

• Downloading media
"""

UI_PROCESS_3 = f"""{DIV}
PROCESSING REQUEST
{DIV}

• Optimizing quality
"""

UI_SESSION_LOG = f"""{DIV}
SESSION LOG
{DIV}

Media removed successfully.

Requested by : {{user}}
Status       : Completed

{DIV}
"""

UI_ACCESS_RESTRICTED = f"""{DIV}
ACCESS RESTRICTED
{DIV}

Channel membership is required
to use this service.

{DIV}
"""

UI_ACCESS_GRANTED = f"""{DIV}
ACCESS GRANTED
{DIV}

Welcome to the private service.

{DIV}
"""

UI_STATUS_ACTIVE = f"""{DIV}
Chat Status
{DIV}

⟡ Authorization : Active
⟡ Expiry        : {{expiry}}
⟡ Auto-Delete   : {{auto}}

{DIV}
"""

UI_STATUS_INACTIVE = f"""{DIV}
Chat Status
{DIV}

⟡ Authorization : Inactive
⟡ Access        : Restricted

{DIV}
"""

# ===================== DB =====================
def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with closing(db()) as conn, conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS auth (
            chat_id INTEGER PRIMARY KEY,
            expires INTEGER
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS settings (
            chat_id INTEGER PRIMARY KEY,
            autodel INTEGER DEFAULT 1
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS limits (
            user_id INTEGER PRIMARY KEY,
            ts INTEGER,
            cnt INTEGER
        )""")

def is_authorized(chat_id):
    with closing(db()) as conn:
        r = conn.execute("SELECT expires FROM auth WHERE chat_id=?", (chat_id,)).fetchone()
        if not r:
            return None
        if r[0] < int(time.time()):
            conn.execute("DELETE FROM auth WHERE chat_id=?", (chat_id,))
            return None
        return r[0]

def authorize(chat_id, days):
    exp = int(time.time()) + days * 86400
    with closing(db()) as conn, conn:
        conn.execute("INSERT OR REPLACE INTO auth VALUES (?,?)", (chat_id, exp))
        conn.execute("INSERT OR IGNORE INTO settings VALUES (?,1)", (chat_id,))

def unauthorize(chat_id):
    with closing(db()) as conn, conn:
        conn.execute("DELETE FROM auth WHERE chat_id=?", (chat_id,))

def autodel(chat_id):
    with closing(db()) as conn:
        r = conn.execute("SELECT autodel FROM settings WHERE chat_id=?", (chat_id,)).fetchone()
        return bool(r[0]) if r else True

def set_autodel(chat_id, v):
    with closing(db()) as conn, conn:
        conn.execute("UPDATE settings SET autodel=? WHERE chat_id=?", (1 if v else 0, chat_id))

# ===================== HELPERS =====================
def mention(u: Message.from_user):
    return f"@{u.username}" if u.username else u.first_name

def human(t):
    d, r = divmod(t, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return f"{d}d {h}h {m}m {s}s"

class HasURL(BaseFilter):
    async def __call__(self, m: Message):
        return bool(re.search(r"https?://", m.text or ""))

def domain(url):
    return urlparse(url).netloc.lower()

# ===================== DOWNLOAD =====================
def duration(url):
    with YoutubeDL({"quiet": True, "skip_download": True}) as y:
        return y.extract_info(url, download=False).get("duration")

def download(url):
    p = f"v_{secrets.token_hex(6)}"
    with YoutubeDL({
        "outtmpl": f"{p}.%(ext)s",
        "merge_output_format": "mp4",
        "quiet": True,
        "format": "bestvideo+bestaudio/best",
    }) as y:
        y.download([url])
    return glob.glob(f"{p}.*")[0]

def segment(path, br):
    base = path.replace(".mp4", "")
    out = f"{base}_%03d.mp4"
    subprocess.run([
        "ffmpeg","-y","-i",path,
        "-c:v","libx264","-crf","23",
        "-maxrate",br,"-bufsize","2M",
        "-c:a","aac","-b:a","128k",
        "-f","segment","-segment_time",str(SEGMENT_TIME),
        "-reset_timestamps","1",out
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sorted(glob.glob(f"{base}_*.mp4"))

# ===================== COMMANDS =====================
@dp.message(Command("start"))
async def start(m: Message):
    await m.reply(UI_ACCESS_GRANTED)

@dp.message(Command("status"))
async def status(m: Message):
    exp = is_authorized(m.chat.id)
    if not exp:
        await m.reply(UI_STATUS_INACTIVE)
        return
    await m.reply(UI_STATUS_ACTIVE.format(
        expiry=human(exp - int(time.time())),
        auto="ON" if autodel(m.chat.id) else "OFF"
    ))

@dp.message(Command("auth"))
async def auth(m: Message):
    if m.from_user.id != OWNER_ID: return
    days = int(m.text.split()[1])
    authorize(m.chat.id, days)
    await m.reply("Authorized")

@dp.message(Command("unauth"))
async def unauth(m: Message):
    if m.from_user.id != OWNER_ID: return
    unauthorize(m.chat.id)
    await m.reply("Unauthorized")

@dp.message(Command("autodelete"))
async def ad(m: Message):
    if m.from_user.id != OWNER_ID: return
    set_autodel(m.chat.id, m.text.split()[1] == "on")
    await m.reply("Updated")

# ===================== URL HANDLER =====================
@dp.message(HasURL())
async def handle(m: Message):
    urls = re.findall(r"https?://[^\s]+", m.text or "")
    for url in urls:
        if "instagram.com" in domain(url):
            path = download(url)
            await m.reply_video(FSInputFile(path))
            os.unlink(path)
            return

        if "xhamster" in domain(url):
            if m.chat.type != ChatType.PRIVATE and not is_authorized(m.chat.id):
                await m.reply(UI_ACCESS_RESTRICTED)
                return

            proc = await m.reply(UI_PROCESS_1)
            await asyncio.sleep(1)
            await proc.edit_text(UI_PROCESS_2)
            await asyncio.sleep(1)
            await proc.edit_text(UI_PROCESS_3)

            dur = duration(url)
            if not dur or dur > MAX_HARD:
                await proc.delete()
                return

            quality = DEFAULT_QUALITY if dur <= MAX_SOFT else "540p"
            path = download(url)
            parts = segment(path, QUALITY_BITRATE[quality])

            await proc.delete()

            to_delete = [m.message_id]
            sent = []

            for i,p in enumerate(parts,1):
                msg = await m.reply_video(
                    FSInputFile(p),
                    caption=f"Part {i}/{len(parts)} · {quality}\nRequested by {mention(m.from_user)}"
                )
                sent.append(msg.message_id)
                os.unlink(p)

            if autodel(m.chat.id):
                await asyncio.sleep(AUTO_DELETE_SECONDS)
                for mid in sent + to_delete:
                    try: await bot.delete_message(m.chat.id, mid)
                    except: pass

                await m.reply(UI_SESSION_LOG.format(user=mention(m.from_user)))

            os.unlink(path)
            return

# ===================== MAIN =====================
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
