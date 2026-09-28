"""
Instagram Downloader — Silent delivery with cache + smart encode.

Flow:
  1. Send sticker
  2. Download silently — direct-only, no proxy, no cookies. 4 layers race
     in parallel, first success wins, the rest are cancelled immediately:
     - Layer 1: yt-dlp, desktop UA
     - Layer 2: yt-dlp, Instagram mobile UA
     - Layer 3: yt-dlp, generic mobile browser UA
     - Layer 4: Instagram's public embed page (see below)
  3. Delete sticker after delivery
  4. Send video — reply to original (with fallback to plain send)
  5. Caption: ✓ Delivered — <mention>

By design, this downloader never uses a proxy or a cookie file. Proxies cost
money and go dead constantly; cookies are a standing account-security liability
(they're live session credentials). Public posts/reels/photos — the vast
majority of what gets requested — download fine without either.

Layer 4 (embed page) is the same trick most public Instagram-downloader sites
use to avoid "log in to continue" walls without a login: Instagram serves an
`/embed/captioned/` page for every public post, meant for embedding it on
other websites, and that page carries the direct video/image URL without
requiring any authentication. A lot of "sign-in required" failures on the
main site aren't really about privacy — they're anti-bot gating that this
sidesteps for free, no credentials involved.

Trade-off: truly private accounts still require a login — no page Instagram
serves publicly can expose that content, with or without a proxy or cookie.
That narrow slice fails cleanly instead of succeeding via a cookie retry.
`ig cookies/` and `cookies_instagram.txt` still exist on disk for now but are
intentionally not read by this module.
"""
import asyncio
import json
import re
import tempfile
import time
from pathlib import Path
from typing import Optional, List

import aiohttp
from yt_dlp import YoutubeDL
from aiogram.types import Message, FSInputFile

from core.bot import bot
from core.config import config
from workers.task_queue import download_semaphore
from utils.logger import logger
from utils.cache import url_cache
from utils.media_processor import (
    ensure_fits_telegram,
    get_video_info,
)
from utils.watchdog import acquire_user_slot, release_user_slot, with_url_dedup
from ui.formatting import safe_caption, build_safe_media_caption
from ui.stickers import send_sticker, delete_sticker
from ui.emoji_config import get_emoji_async
from utils.log_channel import log_download

# ─── Core download logic ──────────────────────────────────────────────────────

# A few distinct User-Agents to race in parallel — different UAs sometimes get
# routed to different Instagram response shapes, which is cheap redundancy now
# that there's no cookie fallback behind these.
_UA_DESKTOP = None  # resolved per-attempt via config.pick_user_agent()
_UA_MOBILE_IG = (
    "Instagram 344.0.0.0.0 Android (33/13; 420dpi; 1080x2400; "
    "samsung; SM-S918B; dm3q; qcom; en_US; 605596538)"
)
_UA_MOBILE_BROWSER = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)


def _make_opts(sub_dir: Path, user_agent: str) -> dict:
    """
    Build yt-dlp options for one direct-only attempt.
    sub_dir: unique directory for this attempt's output files.
    """
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "outtmpl": str(sub_dir / "%(title)s.%(ext)s"),
        "http_headers": {"User-Agent": user_agent},
        # Short timeouts/few retries — this is a hard, fast direct attempt,
        # not a slow one we can afford to wait out before falling back.
        "socket_timeout": 12,
        "retries": 1,
        "fragment_retries": 1,
        # ignoreerrors=True: yt-dlp prints ERROR lines but doesn't raise —
        # we detect failure by checking for downloaded files instead.
        "ignoreerrors": True,
        "format": "best[ext=mp4]/best",
        "age_limit": 100,
    }


def _collect_files(directory: Path) -> List[Path]:
    """Return all media files downloaded into directory."""
    exts = ["*.mp4", "*.webm", "*.mov", "*.mkv", "*.jpg", "*.jpeg", "*.png", "*.webp"]
    files: List[Path] = []
    for pat in exts:
        files.extend(directory.glob(pat))
    return files


async def _run_one(sub_dir: Path, url: str, opts: dict) -> Optional[Path]:
    """
    Run yt-dlp in sub_dir with opts. Returns first downloaded file or None.
    Never raises — all exceptions are caught and logged at DEBUG level.
    """
    sub_dir.mkdir(parents=True, exist_ok=True)
    opts["outtmpl"] = str(sub_dir / "%(title)s.%(ext)s")
    try:
        with YoutubeDL(opts) as ydl:
            await asyncio.to_thread(lambda: ydl.download([url]))
        files = _collect_files(sub_dir)
        if files:
            return files[0]
        return None
    except Exception as e:
        logger.debug(f"IG _run_one failed [{sub_dir.name}]: {type(e).__name__}: {str(e)[:120]}")
        return None


# ─── Layer 4: Instagram public embed page (no login, no proxy, no cookies) ────

_SHORTCODE_RE = re.compile(r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)")


async def _download_bytes(media_url: str, out_path: Path) -> Optional[Path]:
    """Fetch a direct media URL (no proxy, no cookies) and save it."""
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(media_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
                if len(data) < 1000:  # too small to be real media
                    return None
                out_path.write_bytes(data)
                return out_path
    except Exception as e:
        logger.debug(f"IG embed media fetch failed: {e}")
        return None


async def _fetch_via_embed(url: str, sub_dir: Path) -> Optional[Path]:
    """
    Layer 4 — Instagram's own public embed page. No login required for
    public posts; this is the same technique most public Instagram
    downloader tools use instead of a personal login cookie.
    """
    m = _SHORTCODE_RE.search(url)
    if not m:
        return None
    shortcode = m.group(1)
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"

    headers = {
        "User-Agent": config.pick_user_agent(),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(embed_url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                html_text = await resp.text()
    except Exception as e:
        logger.debug(f"IG embed page fetch failed: {e}")
        return None

    sub_dir.mkdir(parents=True, exist_ok=True)

    # Video posts/reels carry a direct CDN video URL in the embed HTML,
    # JSON-escaped (e.g. "\/" for "/") — decode it as a JSON string, not a
    # Python one, since "\/" isn't a valid Python escape and unicode_escape
    # would mangle it into a broken URL.
    video_match = re.search(r'"video_url":"([^"]+)"', html_text)
    if video_match:
        try:
            video_url = json.loads(f'"{video_match.group(1)}"')
        except Exception:
            video_url = video_match.group(1)
        result = await _download_bytes(video_url, sub_dir / "embed.mp4")
        if result:
            return result

    # Photo posts (or video posts without an inline video_url) — og:image
    img_match = re.search(r'<meta property="og:image" content="([^"]+)"', html_text)
    if img_match:
        img_url = img_match.group(1).replace("&amp;", "&")
        result = await _download_bytes(img_url, sub_dir / "embed.jpg")
        if result:
            return result

    return None


async def _race_first_success(tasks: List[asyncio.Task]) -> Optional[Path]:
    """
    Wait for the first task to produce a real (non-None) result and return it
    immediately, cancelling whatever's still running. If every task finishes
    with None, return None once they've all settled.

    This is the speed win from dropping the sequential cookie fallback:
    total latency is now "whichever direct layer answers first", not
    "however long the slowest layer takes before we can even check others".
    """
    pending = set(tasks)
    result: Optional[Path] = None
    try:
        while pending and result is None:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for d in done:
                try:
                    r = d.result()
                except Exception:
                    r = None
                if r:
                    result = r
                    break
    finally:
        for p in pending:
            p.cancel()
    return result


async def download_instagram(url: str, tmp: Path) -> Optional[Path]:
    """
    Instagram download — 4 direct layers raced in parallel, no proxy, no
    cookies. First one to succeed wins; the rest are cancelled immediately.
    """
    layers = [
        ("desktop", config.pick_user_agent()),
        ("mobile_ig", _UA_MOBILE_IG),
        ("mobile_browser", _UA_MOBILE_BROWSER),
    ]

    async def _attempt(label: str, ua: str) -> Optional[Path]:
        sub = tmp / f"ig_{label}"
        opts = _make_opts(sub, ua)
        r = await _run_one(sub, url, opts)
        if r:
            logger.debug(f"IG: layer '{label}' succeeded (direct, no proxy/cookies)")
        return r

    tasks = [asyncio.create_task(_attempt(label, ua)) for label, ua in layers]

    async def _embed_attempt() -> Optional[Path]:
        r = await _fetch_via_embed(url, tmp / "ig_embed")
        if r:
            logger.debug("IG: layer 'embed' succeeded (public embed page, no login)")
        return r

    tasks.append(asyncio.create_task(_embed_attempt()))

    result = await _race_first_success(tasks)

    if not result:
        logger.info(f"IG: all direct layers (including embed page) failed for {url[:60]} — likely a private account")

    return result

# ─── Safe reply helpers ───────────────────────────────────────────────────────

async def _safe_reply_video(m: Message, **kwargs) -> Optional[Message]:
    """Send video — reply to original with full fallback chain."""
    if "caption" in kwargs and kwargs["caption"]:
        kwargs["caption"] = safe_caption(kwargs["caption"])
    try:
        return await bot.send_video(m.chat.id, reply_to_message_id=m.message_id, **kwargs)
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "replied message not found" in err_str:
            try:
                return await bot.send_video(m.chat.id, **kwargs)
            except Exception as e2:
                if "entity_text_invalid" in str(e2).lower() or "bad request" in str(e2).lower():
                    kwargs.pop("caption", None); kwargs.pop("parse_mode", None)
                    try:
                        return await bot.send_video(m.chat.id, **kwargs)
                    except Exception:
                        return None
                return None
        if "entity_text_invalid" in err_str or "bad request" in err_str:
            kwargs.pop("caption", None); kwargs.pop("parse_mode", None)
            try:
                return await bot.send_video(m.chat.id, reply_to_message_id=m.message_id, **kwargs)
            except Exception:
                try:
                    return await bot.send_video(m.chat.id, **kwargs)
                except Exception:
                    return None
        logger.error(f"IG send_video failed: {e}")
        return None


async def _safe_reply_text(m: Message, text: str, **kwargs) -> Optional[Message]:
    """Reply with fallback to plain send."""
    try:
        return await m.reply(text, **kwargs)
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "bad request" in err_str:
            try:
                return await bot.send_message(m.chat.id, text, **kwargs)
            except Exception:
                return None
        logger.error(f"IG reply failed: {e}")
        return None

# ─── Main handler ─────────────────────────────────────────────────────────────

@with_url_dedup
async def handle_instagram(m: Message, url: str):
    """
    Download Instagram posts, reels, stories — including age-restricted content.
    Cache-first → layered download → stream copy / adaptive encode → send.
    """
    if not await acquire_user_slot(m.from_user.id, config.MAX_CONCURRENT_PER_USER):
        _proc = await get_emoji_async("PROCESS")
        await _safe_reply_text(m, f"{_proc} You have downloads in progress. Please wait.", parse_mode="HTML")
        return

    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    delivered_emoji = await get_emoji_async("DELIVERED")
    delivered_caption = build_safe_media_caption(user_id, first_name, delivered_emoji)
    _t_start = time.monotonic()
    sticker_msg_id = None

    try:
        # ── Cache check ───────────────────────────────────────────────────────
        cached = await url_cache.get(url, "video")
        if cached:
            try:
                sent = await _safe_reply_video(
                    m, video=cached, caption=delivered_caption,
                    parse_mode="HTML", supports_streaming=True,
                )
                if sent:
                    return
            except Exception:
                pass  # stale cache — fall through

        async with download_semaphore:
            logger.info(f"INSTAGRAM: {url}")
            sticker_msg_id = await send_sticker(bot, m.chat.id, "instagram")

            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp = Path(tmp_dir)
                    video_file = await download_instagram(url, tmp)

                    if not video_file or not video_file.exists():
                        await delete_sticker(bot, m.chat.id, sticker_msg_id)
                        sticker_msg_id = None
                        _err = await get_emoji_async("ERROR")
                        await _safe_reply_text(
                            m, f"{_err} Unable to process this link.\n\nPlease try again.",
                            parse_mode="HTML",
                        )
                        return

                    parts = await ensure_fits_telegram(video_file, tmp)

                    await delete_sticker(bot, m.chat.id, sticker_msg_id)
                    sticker_msg_id = None

                    sent_count = 0
                    for i, part in enumerate(parts):
                        if not part.exists():
                            logger.warning(f"IG: part {i} missing, skipping")
                            continue
                        info = await get_video_info(part)
                        cap = delivered_caption if i == len(parts) - 1 else f"Part {i+1}/{len(parts)}"
                        sent = await _safe_reply_video(
                            m,
                            video=FSInputFile(part),
                            caption=cap,
                            parse_mode="HTML",
                            supports_streaming=True,
                            width=info.get("width") or None,
                            height=info.get("height") or None,
                            duration=int(info.get("duration") or 0) or None,
                        )
                        sent_count += 1
                        if sent and sent.video and len(parts) == 1:
                            await url_cache.set(url, "video", sent.video.file_id)

                    if sent_count == 0:
                        _err = await get_emoji_async("ERROR")
                        await _safe_reply_text(
                            m, f"{_err} Unable to send this media.\n\nPlease try again.",
                            parse_mode="HTML",
                        )
                        return

                    logger.info(f"INSTAGRAM: Sent {sent_count} part(s) to {user_id}")
                    _elapsed = time.monotonic() - _t_start
                    asyncio.create_task(log_download(
                        user=m.from_user, link=url, chat=m.chat,
                        media_type="Video (Instagram)", time_taken=_elapsed,
                    ))

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"INSTAGRAM ERROR: {e}", exc_info=True)
                if sticker_msg_id:
                    await delete_sticker(bot, m.chat.id, sticker_msg_id)
                    sticker_msg_id = None
                _err = await get_emoji_async("ERROR")
                await _safe_reply_text(
                    m, f"{_err} Unable to process this link.\n\nPlease try again.",
                    parse_mode="HTML",
                )

    finally:
        if sticker_msg_id:
            await delete_sticker(bot, m.chat.id, sticker_msg_id)
        await release_user_slot(m.from_user.id)
