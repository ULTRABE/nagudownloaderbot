"""
Instagram Downloader — Silent delivery with cache + smart encode.

Flow:
  1. Send sticker
  2. Download silently across layered fallbacks:
     - Layer 1: direct (no proxy, no cookies)
     - Layer 2: proxy + Instagram mobile UA  (parallel with Layer 1)
     - Layer 3: cookies, no proxy
     - Layer 4: cookies + proxy
     (Layers 3/4 rotated across all available cookie files)
  3. Delete sticker after delivery
  4. Send video — reply to original (with fallback to plain send)
  5. Caption: ✓ Delivered — <mention>

Cookie support:
  - Place up to 50 Netscape cookie files in "ig cookies/" folder
  - Falls back to single cookies_instagram.txt if folder not present
  - Works WITHOUT cookies — cookies only used as fallback

Age-restricted / N18+ content:
  - Bypassed automatically when cookies are present
  - age_limit=100 on all layers
"""
import asyncio
import random
import tempfile
import time
from pathlib import Path
from typing import Optional, List

from yt_dlp import YoutubeDL
from aiogram.types import Message, FSInputFile

from core.bot import bot
from core.config import config
from workers.task_queue import download_semaphore
from utils.logger import logger
from utils.proxy_manager import proxy_manager
from utils.cache import url_cache
from utils.media_processor import (
    ensure_fits_telegram,
    get_video_info,
)
from utils.watchdog import acquire_user_slot, release_user_slot
from ui.formatting import safe_caption, build_safe_media_caption
from ui.stickers import send_sticker, delete_sticker
from ui.emoji_config import get_emoji_async
from utils.log_channel import log_download

# ─── Cookie helpers ────────────────────────────────────────────────────────────

def _get_all_ig_cookies() -> List[str]:
    """
    Return all available Instagram cookie file paths.
    Priority: ig cookies/ folder → cookies_instagram.txt fallback.
    """
    cookies: List[str] = []

    # Multi-cookie folder
    folder_path = Path(config.IG_COOKIES_FOLDER)
    if folder_path.exists() and folder_path.is_dir():
        cookies.extend([str(p) for p in sorted(folder_path.glob("*.txt"))])

    # Single file fallback (add only if not already included)
    single = config.IG_COOKIES
    if single and Path(single).exists() and single not in cookies:
        cookies.append(single)

    return cookies

# ─── Core download logic ──────────────────────────────────────────────────────

def _make_opts(
    sub_dir: Path,
    use_proxy: bool = False,
    cookie_file: Optional[str] = None,
    mobile_ua: bool = False,
) -> dict:
    """
    Build yt-dlp options for one attempt.
    sub_dir: unique directory for this attempt's output files.
    """
    ua = (
        "Instagram 344.0.0.0.0 Android (33/13; 420dpi; 1080x2400; "
        "samsung; SM-S918B; dm3q; qcom; en_US; 605596538)"
        if mobile_ua else config.pick_user_agent()
    )
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "outtmpl": str(sub_dir / "%(title)s.%(ext)s"),
        "http_headers": {"User-Agent": ua},
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
        # ignoreerrors=True: yt-dlp prints ERROR lines but doesn't raise —
        # we detect failure by checking for downloaded files instead.
        "ignoreerrors": True,
        "format": "best[ext=mp4]/best",
        "age_limit": 100,
    }
    if use_proxy:
        proxy = proxy_manager.pick_proxy()
        if proxy:
            opts["proxy"] = proxy
    if cookie_file:
        opts["cookiefile"] = cookie_file
    return opts


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


async def download_instagram(url: str, tmp: Path) -> Optional[Path]:
    """
    Instagram download with 4-layer fallback.

    Layer 1 + 2 run in PARALLEL (no cookies):
      L1 — direct, desktop UA
      L2 — proxy, Instagram mobile UA

    Layer 3 + 4 run SEQUENTIALLY (with cookies — for restricted/N18+ content):
      L3 — cookies, no proxy  (tried for each available cookie file)
      L4 — cookies + proxy    (tried for each available cookie file)

    Stops as soon as any layer succeeds.
    """
    # ── Parallel: L1 (direct) + L2 (proxy + mobile UA) ──────────────────────
    results: dict = {}

    async def _parallel(idx: int, **kwargs):
        sub = tmp / f"ig_l{idx}"
        opts = _make_opts(sub, **kwargs)
        r = await _run_one(sub, url, opts)
        if r:
            results[idx] = r

    await asyncio.gather(
        asyncio.create_task(_parallel(1, use_proxy=False, mobile_ua=False)),
        asyncio.create_task(_parallel(2, use_proxy=True,  mobile_ua=True)),
        return_exceptions=True,
    )
    for i in sorted(results.keys()):
        logger.debug(f"IG: L{i} succeeded (no cookies)")
        return results[i]

    # ── Sequential: L3/L4 with cookies ──────────────────────────────────────
    all_cookies = _get_all_ig_cookies()

    if not all_cookies:
        logger.info("IG: No cookies available — content requires authentication")
        return None

    # Shuffle for load distribution across accounts
    shuffled = list(all_cookies)
    random.shuffle(shuffled)

    for idx, cookie_file in enumerate(shuffled[:10]):  # cap at 10 accounts
        # L3: cookie only (no proxy) — fastest
        sub3 = tmp / f"ig_l3_{idx}"
        opts3 = _make_opts(sub3, use_proxy=False, cookie_file=cookie_file)
        result = await _run_one(sub3, url, opts3)
        if result:
            logger.info(f"IG: L3 succeeded (cookie #{idx + 1}, no proxy)")
            return result

        # L4: cookie + proxy — bypasses IP blocks
        sub4 = tmp / f"ig_l4_{idx}"
        opts4 = _make_opts(sub4, use_proxy=True, cookie_file=cookie_file)
        result = await _run_one(sub4, url, opts4)
        if result:
            logger.info(f"IG: L4 succeeded (cookie #{idx + 1}, with proxy)")
            return result

    logger.warning(f"IG: All {len(shuffled[:10])} cookie(s) exhausted, giving up")
    return None

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
