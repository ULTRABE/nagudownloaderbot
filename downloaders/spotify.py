"""
Spotify Downloader — Single track + Large playlist (stream track-by-track).

Single track:
  Progress bar only (no text):
  [████░░░░░░] 20% → [████████░░] 80% → [██████████] 100%
  Delete progress → ✓ Delivered — <mention>

Playlist (group → DM):
  Fetch tracks via Spotify API (page-by-page, limit=100)
  Download each track individually with spotdl
  Send to DM immediately after each track
  Update progress every 5 tracks
  Final summary in group

CRITICAL: Never run spotdl on full playlist URL.
Always call spotdl on individual track URLs.

Performance:
  192k bitrate, ultrafast preset, 4 threads
  Target: ≤ 5 seconds per single track
"""
import asyncio
import base64
import re
import time
import tempfile
import traceback
from pathlib import Path
from typing import Optional, List, Tuple, Set

import aiohttp
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError

from core.bot import bot
from core.config import config
from workers.task_queue import spotify_semaphore
from ui.formatting import (
    format_playlist_progress, format_playlist_final,
    format_playlist_dm_complete, format_delivered_with_mention,
)
from utils.helpers import extract_song_metadata
from utils.logger import logger
from utils.user_state import user_state_manager

# ─── Separate semaphore for single tracks (don't wait behind playlists) ───────
_single_semaphore = asyncio.Semaphore(4)

# ─── URL detection ────────────────────────────────────────────────────────────

def is_spotify_playlist(url: str) -> bool:
    url_lower = url.lower()
    return "/playlist/" in url_lower or "/album/" in url_lower

def is_spotify_track(url: str) -> bool:
    url_lower = url.lower()
    return (
        "/track/" in url_lower or
        url_lower.startswith("spotify:track:") or
        "open.spotify.com/track/" in url_lower
    )

def is_spotify_url(url: str) -> bool:
    return "spotify.com" in url.lower() or url.lower().startswith("spotify:")

def _extract_playlist_id(url: str) -> Optional[str]:
    """Extract playlist/album ID from Spotify URL"""
    m = re.search(r"/(?:playlist|album)/([A-Za-z0-9]+)", url)
    return m.group(1) if m else None

# ─── Progress bar ─────────────────────────────────────────────────────────────

def _bar(pct: int) -> str:
    """Clean progress bar — no text, no emojis"""
    width = 10
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct}%"

# ─── Spotify API (client credentials) ────────────────────────────────────────

_spotify_token: Optional[str] = None
_spotify_token_expires: float = 0.0

async def _get_spotify_token() -> Optional[str]:
    """
    Get Spotify access token using client credentials flow.
    Auto-refreshes when expired.
    Returns None if credentials not configured.
    """
    global _spotify_token, _spotify_token_expires

    if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
        return None

    # Return cached token if still valid (with 60s buffer)
    if _spotify_token and time.time() < _spotify_token_expires - 60:
        return _spotify_token

    # Fetch new token
    try:
        credentials = f"{config.SPOTIFY_CLIENT_ID}:{config.SPOTIFY_CLIENT_SECRET}"
        encoded = base64.b64encode(credentials.encode()).decode()

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://accounts.spotify.com/api/token",
                headers={
                    "Authorization": f"Basic {encoded}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    _spotify_token = data.get("access_token")
                    expires_in = data.get("expires_in", 3600)
                    _spotify_token_expires = time.time() + expires_in
                    logger.debug(f"Spotify token refreshed, expires in {expires_in}s")
                    return _spotify_token
                else:
                    text = await resp.text()
                    logger.error(f"Spotify token fetch failed: {resp.status} {text[:200]}")
                    return None
    except Exception as e:
        logger.error(f"Spotify token fetch error: {e}", exc_info=True)
        return None

async def _fetch_playlist_tracks(playlist_id: str, is_album: bool = False) -> List[str]:
    """
    Fetch all track URLs from a Spotify playlist or album using the API.
    Returns list of track URLs (https://open.spotify.com/track/ID).
    Uses pagination (limit=100 per page).
    """
    token = await _get_spotify_token()
    if not token:
        logger.error("Spotify: no token available for playlist fetch")
        return []

    track_urls: List[str] = []
    endpoint = "albums" if is_album else "playlists"
    url = f"https://api.spotify.com/v1/{endpoint}/{playlist_id}/tracks?limit=100&offset=0"

    try:
        async with aiohttp.ClientSession() as session:
            while url:
                async with session.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 401:
                        # Token expired — refresh and retry once
                        logger.warning("Spotify: 401 on playlist fetch, refreshing token")
                        global _spotify_token, _spotify_token_expires
                        _spotify_token = None
                        _spotify_token_expires = 0.0
                        token = await _get_spotify_token()
                        if not token:
                            break
                        continue

                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(f"Spotify playlist fetch failed: {resp.status} {text[:200]}")
                        break

                    data = await resp.json()
                    items = data.get("items", [])

                    for item in items:
                        # Playlist items have item["track"], album items are direct
                        track = item.get("track") if not is_album else item
                        if not track:
                            continue
                        track_id = track.get("id")
                        if track_id:
                            track_urls.append(f"https://open.spotify.com/track/{track_id}")

                    # Pagination
                    url = data.get("next")
                    logger.debug(f"Spotify: fetched {len(track_urls)} tracks so far")

    except Exception as e:
        logger.error(f"Spotify playlist fetch error: {e}", exc_info=True)

    return track_urls

# ─── Safe reply helpers ───────────────────────────────────────────────────────

async def _safe_reply(m: Message, text: str, **kwargs) -> Optional[Message]:
    """Reply with fallback to plain send."""
    try:
        return await m.reply(text, **kwargs)
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "bad request" in err_str:
            try:
                return await bot.send_message(m.chat.id, text, **kwargs)
            except Exception as e2:
                logger.error(f"Spotify safe_reply fallback failed: {e2}")
                return None
        logger.error(f"Spotify reply failed: {e}")
        return None

async def _safe_edit(msg: Optional[Message], text: str, **kwargs) -> None:
    """Non-blocking safe message edit"""
    if not msg:
        return
    try:
        await msg.edit_text(text, **kwargs)
    except Exception:
        pass

async def _safe_delete(msg: Optional[Message]) -> None:
    """Non-blocking safe message delete"""
    if not msg:
        return
    try:
        await msg.delete()
    except Exception:
        pass

# ─── Download single track via spotdl ────────────────────────────────────────

async def _download_track(url: str, tmp: Path) -> Optional[Path]:
    """
    Download a single Spotify track using spotdl.
    Returns path to MP3 file or None on failure.
    Uses 192k bitrate, ultrafast preset.
    """
    cmd = [
        "spotdl", "download", url,
        "--client-id", config.SPOTIFY_CLIENT_ID,
        "--client-secret", config.SPOTIFY_CLIENT_SECRET,
        "--output", str(tmp),
        "--format", "mp3",
        "--bitrate", "192k",
        "--threads", "4",
        "--no-cache",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=120,  # 2 minutes max per track
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await asyncio.wait_for(proc.communicate(), timeout=5)
            except Exception:
                pass
            logger.warning(f"spotdl timeout for {url}")
            return None

        mp3_files = sorted(tmp.glob("*.mp3"))
        if mp3_files:
            return mp3_files[0]

        stderr_text = stderr.decode(errors="replace")[:300] if stderr else ""
        logger.warning(f"spotdl no MP3: returncode={proc.returncode}, stderr={stderr_text}")
        return None

    except Exception as e:
        logger.error(f"spotdl error for {url}: {e}", exc_info=True)
        return None

# ─── Single track handler ─────────────────────────────────────────────────────

async def handle_spotify_single(m: Message, url: str):
    """
    Download single Spotify track.
    Works in private + group chats.

    UI: Progress bar only (no text).
    [████░░░░░░] 20% → ... → [██████████] 100%
    Delete progress → ✓ Delivered — <mention>

    Target: ≤ 5 seconds total.
    """
    if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
        logger.warning("Spotify: CLIENT_ID or CLIENT_SECRET not configured")
        await _safe_reply(
            m,
            "⚠ Unable to process this link.\n\nPlease try again.",
            parse_mode="HTML",
        )
        return

    is_group = m.chat.type in ("group", "supergroup")
    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    delivered_caption = format_delivered_with_mention(user_id, first_name)

    # Send initial progress bar immediately
    progress = await _safe_reply(m, _bar(20), parse_mode="HTML")

    try:
        async with _single_semaphore:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)

                # Animate progress while downloading
                async def _animate():
                    steps = [40, 60, 80]
                    for pct in steps:
                        await asyncio.sleep(1.2)
                        await _safe_edit(progress, _bar(pct), parse_mode="HTML")

                anim_task = asyncio.create_task(_animate())

                mp3_file = await _download_track(url, tmp)
                anim_task.cancel()

                if not mp3_file or not mp3_file.exists():
                    await _safe_delete(progress)
                    await _safe_reply(
                        m,
                        "⚠ Unable to process this link.\n\nPlease try again.",
                        parse_mode="HTML",
                    )
                    return

                # Show 100% before sending
                await _safe_edit(progress, _bar(100), parse_mode="HTML")

                artist, title = extract_song_metadata(mp3_file.stem)
                logger.info(f"SPOTIFY SINGLE: Downloaded '{title}' by '{artist}'")

                # Delete progress before sending
                await _safe_delete(progress)
                progress = None

                if is_group:
                    # Send to DM
                    try:
                        await bot.send_audio(
                            m.from_user.id,
                            FSInputFile(mp3_file),
                            title=title,
                            performer=artist,
                            caption=delivered_caption,
                            parse_mode="HTML",
                        )
                        # Reply in group
                        await _safe_reply(m, "✓ Sent to your DM", parse_mode="HTML")
                    except TelegramForbiddenError:
                        bot_me = await bot.get_me()
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(
                                text="🎧 Start Bot",
                                url=f"https://t.me/{bot_me.username}?start=spotify",
                            )
                        ]])
                        await _safe_reply(
                            m,
                            "⚠ Start the bot first to receive songs in DM.\n\nTap below, then resend the link 👇",
                            reply_markup=keyboard,
                            parse_mode="HTML",
                        )
                        return
                else:
                    # DM: send directly
                    await bot.send_audio(
                        m.chat.id,
                        FSInputFile(mp3_file),
                        title=title,
                        performer=artist,
                        caption=delivered_caption,
                        parse_mode="HTML",
                    )

                logger.info(f"SPOTIFY SINGLE: '{title}' by '{artist}' → {user_id}")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"SPOTIFY SINGLE ERROR: {e}", exc_info=True)
        await _safe_delete(progress)
        await _safe_reply(
            m,
            "⚠ Unable to process this link.\n\nPlease try again.",
            parse_mode="HTML",
        )

# ─── Playlist handler ─────────────────────────────────────────────────────────

async def handle_spotify_playlist(m: Message, url: str):
    """
    Route Spotify URL:
    - Single track → handle_spotify_single
    - Playlist/album → stream track-by-track via Spotify API

    CRITICAL: Never run spotdl on full playlist URL.
    Always fetch track list via API, then call spotdl per track.

    Wrapped in full try/except — never shows internal errors to user.
    """
    try:
        if is_spotify_track(url):
            await handle_spotify_single(m, url)
            return

        # Playlists: group-only
        if m.chat.type == "private":
            await _safe_reply(
                m,
                "⚠ Spotify playlists only work in groups.",
                parse_mode="HTML",
            )
            return

        logger.info(f"SPOTIFY PLAYLIST: Group request from {m.from_user.id}")

        # Cooldown check
        is_cooldown, minutes_left = await user_state_manager.is_on_cooldown(m.from_user.id)
        if is_cooldown:
            await _safe_reply(
                m,
                f"⏳ Cooldown active — {minutes_left} min remaining",
                parse_mode="HTML",
            )
            return

        # Bot-started check
        has_started = await user_state_manager.has_started_bot(m.from_user.id)
        if not has_started:
            bot_me = await bot.get_me()
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🎧 Start Bot",
                    url=f"https://t.me/{bot_me.username}?start=spotify",
                )
            ]])
            await _safe_reply(
                m,
                "⚠ Start the bot first to receive songs in DM.\n\nTap below, then resend the playlist link 👇",
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return

        # Blocked check
        if await user_state_manager.has_blocked_bot(m.from_user.id):
            await _safe_reply(
                m,
                "🚫 You have blocked the bot — unblock and try again.",
                parse_mode="HTML",
            )
            return

        if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
            logger.warning("Spotify: CLIENT_ID or CLIENT_SECRET not configured")
            await _safe_reply(
                m,
                "⚠ Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
            return

        await _run_playlist_download(m, url)

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"SPOTIFY PLAYLIST OUTER ERROR: {e}", exc_info=True)
        try:
            await _safe_reply(
                m,
                "⚠ Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
        except Exception:
            pass


async def _run_playlist_download(m: Message, url: str):
    """
    Inner playlist download.
    Fetches tracks via Spotify API (page-by-page).
    Downloads each track individually with spotdl.
    Sends to DM immediately after each track.
    """
    async with spotify_semaphore:
        # Delete user's link after 4 seconds
        async def _delete_link():
            await asyncio.sleep(4)
            try:
                await m.delete()
            except Exception:
                pass
        asyncio.create_task(_delete_link())

        # Determine if album or playlist
        is_album = "/album/" in url.lower()
        playlist_id = _extract_playlist_id(url)

        if not playlist_id:
            logger.error(f"SPOTIFY PLAYLIST: Could not extract ID from {url}")
            await _safe_reply(
                m,
                "⚠ Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
            return

        # Initial progress message
        progress_msg = await m.answer(
            f"Playlist: Loading...\n\n{_bar(0)}\n0 / ?",
            parse_mode="HTML",
        )

        try:
            # Fetch track list via Spotify API
            logger.info(f"SPOTIFY PLAYLIST: Fetching tracks for {playlist_id}")
            track_urls = await _fetch_playlist_tracks(playlist_id, is_album=is_album)

            if not track_urls:
                await _safe_edit(
                    progress_msg,
                    "⚠ Unable to process this link.\n\nPlease try again.",
                    parse_mode="HTML",
                )
                return

            total = len(track_urls)
            playlist_name = "Playlist"
            logger.info(f"SPOTIFY PLAYLIST: {total} tracks to download")

            # Update progress with total
            await _safe_edit(
                progress_msg,
                f"Playlist: {playlist_name}\n\n{_bar(0)}\n0 / {total}",
                parse_mode="HTML",
            )

            sent_count = 0
            failed_count = 0
            blocked = False
            start_time = time.perf_counter()

            # Download and send each track individually
            for i, track_url in enumerate(track_urls):
                if blocked:
                    break

                try:
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        tmp = Path(tmp_dir)
                        mp3_file = await _download_track(track_url, tmp)

                        if not mp3_file or not mp3_file.exists():
                            failed_count += 1
                            logger.warning(f"SPOTIFY PLAYLIST: Track {i+1}/{total} failed: {track_url}")
                        else:
                            artist, title = extract_song_metadata(mp3_file.stem)
                            try:
                                await bot.send_audio(
                                    m.from_user.id,
                                    FSInputFile(mp3_file),
                                    title=title,
                                    performer=artist,
                                )
                                sent_count += 1
                                logger.info(f"SPOTIFY PLAYLIST: Sent {sent_count}/{total}: '{title}'")
                            except TelegramForbiddenError:
                                logger.error(f"User {m.from_user.id} blocked bot")
                                blocked = True
                                break
                            except Exception as e:
                                logger.error(f"SPOTIFY PLAYLIST: Send failed for '{title}': {e}")
                                failed_count += 1

                except Exception as e:
                    logger.error(f"SPOTIFY PLAYLIST: Track {i+1} error: {e}", exc_info=True)
                    failed_count += 1

                # Update progress every 5 tracks
                total_done = sent_count + failed_count
                if total_done % 5 == 0 or total_done == total:
                    pct = min(100, int(total_done * 100 / total)) if total > 0 else 0
                    await _safe_edit(
                        progress_msg,
                        f"Playlist: {playlist_name}\n\n{_bar(pct)}\n{total_done} / {total}",
                        parse_mode="HTML",
                    )

            elapsed = time.perf_counter() - start_time

            if blocked:
                await user_state_manager.mark_user_blocked(m.from_user.id)
                await user_state_manager.apply_cooldown(m.from_user.id)
                await _safe_edit(
                    progress_msg,
                    "🚫 Blocked — cooldown applied.",
                    parse_mode="HTML",
                )
                return

            # Show 100% completion
            await _safe_edit(
                progress_msg,
                f"Playlist: {playlist_name}\n\n{_bar(100)}\n{total} / {total}",
                parse_mode="HTML",
            )

            # Delete progress after 5 seconds
            async def _delete_progress():
                await asyncio.sleep(5)
                await _safe_delete(progress_msg)
            asyncio.create_task(_delete_progress())

            # Final summary in group
            await m.answer(
                format_playlist_final(
                    m.from_user, playlist_name,
                    total, sent_count, failed_count
                ),
                parse_mode="HTML",
            )

            # DM completion message
            try:
                await bot.send_message(
                    m.from_user.id,
                    format_playlist_dm_complete(playlist_name),
                    parse_mode="HTML",
                )
            except Exception:
                pass

            logger.info(
                f"SPOTIFY PLAYLIST: Done — {sent_count} sent, "
                f"{failed_count} failed in {elapsed:.1f}s"
            )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"SPOTIFY PLAYLIST ERROR: {e}", exc_info=True)
            try:
                await _safe_edit(
                    progress_msg,
                    "⚠ Unable to process this link.\n\nPlease try again.",
                    parse_mode="HTML",
                )
            except Exception:
                try:
                    await m.answer(
                        "⚠ Unable to process this link.\n\nPlease try again.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
