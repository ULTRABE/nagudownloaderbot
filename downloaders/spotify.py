"""
Spotify Downloader — Single track + Large playlist (stream track-by-track).

Single track:
  Progress bar only (no text):
  [████░░░░░░] 20% → [████████░░] 80% → [██████████] 100%
  Delete progress → ✓ Delivered — <mention>
  Sends in SAME chat (group or private).

Playlist (→ DM):
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
    safe_caption, build_safe_media_caption,
)
from ui.emoji_config import get_emoji_async
from utils.helpers import extract_song_metadata
from utils.logger import logger
from utils.user_state import user_state_manager
from utils.log_channel import log_download

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

async def _fetch_playlist_tracks_api(playlist_id: str, is_album: bool = False) -> List[str]:
    """
    Fetch all track URLs from a Spotify playlist or album using the API.
    Returns list of track URLs (https://open.spotify.com/track/ID).
    Uses pagination (limit=100 per page).
    NOTE: Does NOT work for Spotify-curated playlists (Daily Mix, Discover Weekly, etc.)
    """
    token = await _get_spotify_token()
    if not token:
        logger.error("SPOTIFY API: No token available — check SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET env vars")
        return []

    track_urls: List[str] = []
    endpoint = "albums" if is_album else "playlists"
    url = f"https://api.spotify.com/v1/{endpoint}/{playlist_id}/tracks?limit=100&offset=0"

    try:
        async with aiohttp.ClientSession() as session:
            _retried_401 = False  # Track 401 retry to prevent infinite loop
            while url:
                async with session.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 401:
                        if _retried_401:
                            # Already retried once — give up to avoid infinite loop
                            logger.error("Spotify: 401 after token refresh, giving up")
                            break
                        # Token expired — refresh and retry once
                        logger.warning("Spotify: 401 on playlist fetch, refreshing token")
                        _retried_401 = True
                        global _spotify_token, _spotify_token_expires
                        _spotify_token = None
                        _spotify_token_expires = 0.0
                        token = await _get_spotify_token()
                        if not token:
                            break
                        continue

                    # Successful request — reset 401 retry flag
                    _retried_401 = False

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


async def _fetch_playlist_tracks_spotdl(playlist_url: str) -> List[str]:
    """
    Fetch track URLs from a Spotify playlist using spotdl --print-errors.
    Works for ALL playlist types including Spotify-curated playlists.
    Returns list of track URLs.
    """
    try:
        cmd = [
            "spotdl", "url", playlist_url,
            "--client-id", config.SPOTIFY_CLIENT_ID,
            "--client-secret", config.SPOTIFY_CLIENT_SECRET,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await asyncio.wait_for(proc.communicate(), timeout=5)
            except Exception:
                pass
            logger.warning("spotdl url timeout")
            return []

        if stdout:
            lines = stdout.decode(errors="replace").strip().splitlines()
            urls = [line.strip() for line in lines if line.strip().startswith("https://open.spotify.com/track/")]
            logger.info(f"Spotify: spotdl url found {len(urls)} tracks")
            return urls

        return []
    except Exception as e:
        logger.error(f"spotdl url error: {e}", exc_info=True)
        return []


async def _fetch_playlist_name(playlist_id: str, is_album: bool = False) -> str:
    """
    Fetch playlist or album name from Spotify API.
    Returns the name string, or "Playlist" / "Album" as fallback.
    Never crashes — returns fallback on any error.
    """
    token = await _get_spotify_token()
    if not token:
        return "Album" if is_album else "Playlist"
    endpoint = "albums" if is_album else "playlists"
    api_url = f"https://api.spotify.com/v1/{endpoint}/{playlist_id}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                api_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    name = data.get("name", "")
                    if name:
                        return name[:40]
    except Exception as e:
        logger.debug(f"Spotify playlist name fetch error: {e}")
    return "Album" if is_album else "Playlist"


async def _fetch_playlist_tracks(playlist_id: str, is_album: bool = False, playlist_url: str = "") -> List[str]:
    """
    Fetch all track URLs from a Spotify playlist or album.
    Tries Spotify API first, falls back to spotdl for curated playlists.
    """
    # Try API first
    track_urls = await _fetch_playlist_tracks_api(playlist_id, is_album=is_album)
    if track_urls:
        return track_urls

    # Fallback: use spotdl to get track URLs (works for curated playlists)
    if playlist_url:
        logger.info("Spotify: API returned no tracks, trying spotdl fallback")
        track_urls = await _fetch_playlist_tracks_spotdl(playlist_url)

    return track_urls

# ─── Safe reply helpers ───────────────────────────────────────────────────────

async def _safe_reply(m: Message, text: str, **kwargs) -> Optional[Message]:
    """Reply with fallback to plain send."""
    try:
        return await m.reply(text, **kwargs)
    except Exception as e:
        err_str = str(e).lower()
        if "message to be replied not found" in err_str or "replied message not found" in err_str:
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
    Uses 192k bitrate.
    """
    cmd = [
        "spotdl", "download", url,
        "--client-id", config.SPOTIFY_CLIENT_ID,
        "--client-secret", config.SPOTIFY_CLIENT_SECRET,
        "--output", "{title} - {artists}",
        "--format", "mp3",
        "--bitrate", "192k",
        "--no-cache",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(tmp),  # Run in tmp dir so files are created there
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

        # Check for any audio files (spotdl may produce mp3, m4a, ogg, etc.)
        audio_files = (
            sorted(tmp.glob("*.mp3")) +
            sorted(tmp.glob("*.m4a")) +
            sorted(tmp.glob("*.ogg")) +
            sorted(tmp.glob("*.opus")) +
            sorted(tmp.glob("*.flac"))
        )
        if audio_files:
            return audio_files[0]

        stdout_text = stdout.decode(errors="replace")[:500] if stdout else ""
        stderr_text = stderr.decode(errors="replace")[:300] if stderr else ""
        logger.warning(f"spotdl no audio file: returncode={proc.returncode}, stdout={stdout_text[:200]}, stderr={stderr_text}")
        return None

    except Exception as e:
        logger.error(f"spotdl error for {url}: {e}", exc_info=True)
        return None

# ─── Single track handler ─────────────────────────────────────────────────────

async def handle_spotify_single(m: Message, url: str):
    """
    Download single Spotify track.
    Works in private + group chats.
    ALWAYS sends in the SAME chat where the link was sent.

    UI: Progress bar only (no text).
    [████░░░░░░] 20% → ... → [██████████] 100%
    Delete progress → ✓ Delivered — <mention>

    Target: ≤ 6 seconds total.
    """
    if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
        logger.warning("Spotify: CLIENT_ID or CLIENT_SECRET not configured")
        _err = await get_emoji_async("ERROR")
        await _safe_reply(
            m,
            f"{_err} Unable to process this link.\n\nPlease try again.",
            parse_mode="HTML",
        )
        return

    user_id = m.from_user.id
    first_name = m.from_user.first_name or "User"
    # Build sanitized caption via centralized builder — prevents ENTITY_TEXT_INVALID
    delivered_emoji = await get_emoji_async("DELIVERED")
    delivered_caption = build_safe_media_caption(user_id, first_name, delivered_emoji)
    # Always send in same chat (group or private)
    target_chat = m.chat.id
    _t_start = time.monotonic()

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
                    _err = await get_emoji_async("ERROR")
                    await _safe_reply(
                        m,
                        f"{_err} Unable to process this link.\n\nPlease try again.",
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

                # Send in same chat (group or private).
                # Caption already sanitized via build_safe_media_caption().
                # Retry once without caption on ENTITY_TEXT_INVALID — never silently drop.
                try:
                    await bot.send_audio(
                        target_chat,
                        FSInputFile(mp3_file),
                        title=title,
                        performer=artist,
                        caption=delivered_caption,
                        parse_mode="HTML",
                    )
                except Exception as _send_err:
                    _err_str = str(_send_err).lower()
                    if "entity_text_invalid" in _err_str or "bad request" in _err_str:
                        # Caption still broken after sanitization — retry once without caption
                        logger.warning(
                            f"SPOTIFY SINGLE: ENTITY_TEXT_INVALID after sanitization, "
                            f"retrying without caption. Error: {_send_err}"
                        )
                        await bot.send_audio(
                            target_chat,
                            FSInputFile(mp3_file),
                            title=title,
                            performer=artist,
                        )
                    else:
                        raise

                logger.info(f"SPOTIFY SINGLE: '{title}' by '{artist}' → chat {target_chat}")

                # Log to channel
                _elapsed = time.monotonic() - _t_start
                asyncio.create_task(log_download(
                    user=m.from_user,
                    link=url,
                    chat=m.chat,
                    media_type="Audio (Spotify)",
                    time_taken=_elapsed,
                ))

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"SPOTIFY SINGLE ERROR: {e}", exc_info=True)
        await _safe_delete(progress)
        _err = await get_emoji_async("ERROR")
        await _safe_reply(
            m,
            f"{_err} Unable to process this link.\n\nPlease try again.",
            parse_mode="HTML",
        )

# ─── Playlist handler ─────────────────────────────────────────────────────────

async def handle_spotify_playlist(m: Message, url: str):
    """
    Route Spotify URL:
    - Single track → handle_spotify_single (sends in same chat)
    - Playlist/album → stream track-by-track via Spotify API (sends to DM)

    CRITICAL: Never run spotdl on full playlist URL.
    Always fetch track list via API, then call spotdl per track.

    Wrapped in full try/except — never shows internal errors to user.
    """
    try:
        if is_spotify_track(url):
            logger.info(f"SPOTIFY: Routing track URL to single handler: {url[:60]}")
            await handle_spotify_single(m, url)
            return

        logger.info(f"SPOTIFY PLAYLIST: Request from {m.from_user.id} in {m.chat.type} — URL: {url[:60]}")

        # Cooldown check
        is_cooldown, minutes_left = await user_state_manager.is_on_cooldown(m.from_user.id)
        if is_cooldown:
            logger.info(f"SPOTIFY PLAYLIST: User {m.from_user.id} on cooldown ({minutes_left} min)")
            _proc = await get_emoji_async("PROCESS")
            await _safe_reply(
                m,
                f"{_proc} 𝐂ᴏᴏʟᴅᴏᴡɴ ᴀᴄᴛɪᴠᴇ — {minutes_left} ᴍɪɴ ʀᴇᴍᴀɪɴɪɴɢ",
                parse_mode="HTML",
            )
            return

        # Bot-started check (needed to send DM)
        # Note: has_started_bot returns True on Redis failure (safe default)
        has_started = await user_state_manager.has_started_bot(m.from_user.id)
        if not has_started:
            logger.info(f"SPOTIFY PLAYLIST: User {m.from_user.id} has not started bot — showing start prompt")
            bot_me = await bot.get_me()
            sp = await get_emoji_async("SPOTIFY")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=f"{sp} Start Bot",
                    url=f"https://t.me/{bot_me.username}?start=spotify",
                    style="success",
                )
            ]])
            _info = await get_emoji_async("INFO")
            await _safe_reply(
                m,
                f"{_info} 𝐒ᴛᴀʀᴛ 𝐁ᴏᴛ 𝐅ɪʀꜱᴛ\n\n𝐒ᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ᴛᴏ ʀᴇᴄᴇɪᴠᴇ ꜱᴏɴɢꜱ ɪɴ 𝐃𝐌.\n\n𝐓ᴀᴘ ʙᴇʟᴏᴡ, ᴛʜᴇɴ ʀᴇꜱᴇɴᴅ ᴛʜᴇ ʟɪɴᴋ.",
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return

        # Blocked check
        if await user_state_manager.has_blocked_bot(m.from_user.id):
            logger.info(f"SPOTIFY PLAYLIST: User {m.from_user.id} has blocked bot")
            _err = await get_emoji_async("ERROR")
            await _safe_reply(
                m,
                f"{_err} 𝐅ᴀɪʟᴇᴅ\n𝐔ɴʙʟᴏᴄᴋ ᴛʜᴇ ʙᴏᴛ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
                parse_mode="HTML",
            )
            return

        if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
            logger.warning("SPOTIFY PLAYLIST: CLIENT_ID or CLIENT_SECRET not configured — cannot process")
            _err = await get_emoji_async("ERROR")
            await _safe_reply(
                m,
                f"{_err} Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
            return

        logger.info(f"SPOTIFY PLAYLIST: All checks passed, starting download for user {m.from_user.id}")
        await _run_playlist_download(m, url)

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"SPOTIFY PLAYLIST OUTER ERROR: {e}", exc_info=True)
        try:
            _err = await get_emoji_async("ERROR")
            await _safe_reply(
                m,
                f"{_err} Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
        except Exception:
            pass


async def _run_playlist_download(m: Message, url: str):
    """
    Inner playlist download.
    Fetches tracks via Spotify API (page-by-page).
    Downloads each track individually with spotdl.
    Sends each track to user's DM immediately.

    Progress:
    - Group chat: overall playlist progress bar (updates every 5 tracks)
    - DM: each song sent as it's downloaded
    - DM: start notification with playlist info
    - DM: completion message when done
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
            _err = await get_emoji_async("ERROR")
            await _safe_reply(
                m,
                f"{_err} Unable to process this link.\n\nPlease try again.",
                parse_mode="HTML",
            )
            return

        # Initial progress message in group/chat
        _sp = await get_emoji_async("SPOTIFY")
        progress_msg = await m.answer(
            f"{_sp} <b>𝐏ʟᴀʏʟɪꜱᴛ:</b> Loading...\n\n{_bar(0)}\n0 / ?",
            parse_mode="HTML",
        )

        try:
            # Fetch track list via Spotify API (with spotdl fallback for curated playlists)
            logger.info(f"SPOTIFY PLAYLIST: Fetching tracks for playlist_id={playlist_id} is_album={is_album}")
            track_urls = await _fetch_playlist_tracks(playlist_id, is_album=is_album, playlist_url=url)

            if not track_urls:
                logger.error(
                    f"SPOTIFY PLAYLIST: No tracks found for {url[:60]} "
                    f"(playlist_id={playlist_id}, is_album={is_album}). "
                    f"Check SPOTIFY_CLIENT_ID/SECRET and API access."
                )
                _err = await get_emoji_async("ERROR")
                await _safe_edit(
                    progress_msg,
                    f"{_err} Unable to process this link.\n\nPlease try again.",
                    parse_mode="HTML",
                )
                return

            total = len(track_urls)
            playlist_name = await _fetch_playlist_name(playlist_id, is_album=is_album)
            logger.info(f"SPOTIFY PLAYLIST: '{playlist_name}' — {total} tracks to download")

            # Update progress with total count
            _sp = await get_emoji_async("SPOTIFY")
            await _safe_edit(
                progress_msg,
                f"{_sp} <b>𝐏ʟᴀʏʟɪꜱᴛ:</b> {playlist_name}\n\n{_bar(0)}\n0 / {total}",
                parse_mode="HTML",
            )

            # Send DM notification with playlist info
            user_id = m.from_user.id
            first_name = (m.from_user.first_name or "there")[:32]
            try:
                _music = await get_emoji_async("MUSIC")
                await bot.send_message(
                    user_id,
                    f"{_music} <b>𝐏ʟᴀʏʟɪꜱᴛ 𝐒𝐭𝐚𝐫𝐭𝐞𝐝</b>\n\n"
                    f"<b>{playlist_name}</b>\n"
                    f"Songs: {total}\n\n"
                    f"Downloading now — songs will appear here one by one.",
                    parse_mode="HTML",
                )
            except Exception:
                pass

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

                        # Update current song progress in group chat
                        total_done = sent_count + failed_count
                        pct = min(99, int(total_done * 100 / total)) if total > 0 else 0
                        song_num = i + 1
                        _dl = await get_emoji_async("DOWNLOAD")
                        try:
                            await _safe_edit(
                                progress_msg,
                                f"{_sp} <b>𝐏ʟᴀʏʟɪꜱᴛ:</b> {playlist_name}\n\n"
                                f"{_bar(pct)}\n"
                                f"{total_done} / {total}\n\n"
                                f"{_dl} Song {song_num}/{total}",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

                        mp3_file = await _download_track(track_url, tmp)

                        if not mp3_file or not mp3_file.exists():
                            failed_count += 1
                            logger.warning(f"SPOTIFY PLAYLIST: Track {i+1}/{total} failed: {track_url}")
                        else:
                            artist, title = extract_song_metadata(mp3_file.stem)
                            # Build sanitized per-track caption — prevents ENTITY_TEXT_INVALID
                            track_caption = build_safe_media_caption(
                                user_id,
                                m.from_user.first_name or "User",
                                await get_emoji_async("DELIVERED"),
                            )
                            try:
                                # Send to user's DM with sanitized caption
                                await bot.send_audio(
                                    user_id,
                                    FSInputFile(mp3_file),
                                    title=title,
                                    performer=artist,
                                    caption=track_caption,
                                    parse_mode="HTML",
                                )
                                sent_count += 1
                                logger.info(f"SPOTIFY PLAYLIST: Sent {sent_count}/{total}: '{title}'")
                            except TelegramForbiddenError:
                                logger.error(f"User {user_id} blocked bot")
                                blocked = True
                                break
                            except Exception as _send_err:
                                _err_str = str(_send_err).lower()
                                if "entity_text_invalid" in _err_str or "bad request" in _err_str:
                                    # Caption broken — retry once without caption
                                    logger.warning(
                                        f"SPOTIFY PLAYLIST: ENTITY_TEXT_INVALID for '{title}', "
                                        f"retrying without caption"
                                    )
                                    try:
                                        await bot.send_audio(
                                            user_id,
                                            FSInputFile(mp3_file),
                                            title=title,
                                            performer=artist,
                                        )
                                        sent_count += 1
                                        logger.info(f"SPOTIFY PLAYLIST: Sent (no caption) {sent_count}/{total}: '{title}'")
                                    except TelegramForbiddenError:
                                        logger.error(f"User {user_id} blocked bot")
                                        blocked = True
                                        break
                                    except Exception as e2:
                                        logger.error(f"SPOTIFY PLAYLIST: Send retry failed for '{title}': {e2}")
                                        failed_count += 1
                                else:
                                    logger.error(f"SPOTIFY PLAYLIST: Send failed for '{title}': {_send_err}")
                                    failed_count += 1

                except Exception as e:
                    logger.error(f"SPOTIFY PLAYLIST: Track {i+1} error: {e}", exc_info=True)
                    failed_count += 1

                # Update overall progress every 5 tracks
                total_done = sent_count + failed_count
                if total_done % 5 == 0 or total_done == total:
                    pct = min(100, int(total_done * 100 / total)) if total > 0 else 0
                    try:
                        await _safe_edit(
                            progress_msg,
                            f"{_sp} <b>𝐏ʟᴀʏʟɪꜱᴛ:</b> {playlist_name}\n\n{_bar(pct)}\n{total_done} / {total}",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

            elapsed = time.perf_counter() - start_time

            if blocked:
                await user_state_manager.mark_user_blocked(user_id)
                await user_state_manager.apply_cooldown(user_id)
                _err = await get_emoji_async("ERROR")
                await _safe_edit(
                    progress_msg,
                    f"{_err} <b>𝐁𝐨𝐭 𝐁𝐥𝐨𝐜𝐤𝐞𝐝</b> — cooldown applied.",
                    parse_mode="HTML",
                )
                return

            # Show 100% completion in group chat
            await _safe_edit(
                progress_msg,
                f"{_sp} <b>𝐏ʟᴀʏʟɪꜱᴛ:</b> {playlist_name}\n\n{_bar(100)}\n{total} / {total}",
                parse_mode="HTML",
            )

            # Delete progress after 5 seconds
            async def _delete_progress():
                await asyncio.sleep(5)
                await _safe_delete(progress_msg)
            asyncio.create_task(_delete_progress())

            # Final summary in group/chat
            await m.answer(
                await format_playlist_final(
                    m.from_user, playlist_name,
                    total, sent_count, failed_count
                ),
                parse_mode="HTML",
            )

            # DM completion message — warm and refined
            try:
                bot_me = await bot.get_me()
                bot_username = f"@{bot_me.username}" if bot_me.username else "Nagu Downloader"
                _complete = await get_emoji_async("COMPLETE")
                _sp = await get_emoji_async("SPOTIFY")
                await bot.send_message(
                    user_id,
                    f"{_complete} <b>𝐏ʟᴀʏʟɪꜱᴛ 𝐂ᴏᴍᴘʟᴇᴛᴇᴅ</b>\n\n"
                    f"<b>{playlist_name}</b>\n"
                    f"Sent: {sent_count} / {total}\n\n"
                    f"Thanks for using {bot_username} — enjoy your music! {_sp}",
                    parse_mode="HTML",
                )
            except Exception:
                pass

            logger.info(
                f"SPOTIFY PLAYLIST: Done — {sent_count} sent, "
                f"{failed_count} failed in {elapsed:.1f}s"
            )

            # Log to channel
            asyncio.create_task(log_download(
                user=m.from_user,
                link=url,
                chat=m.chat,
                media_type=f"Playlist (Spotify, {sent_count}/{total})",
                time_taken=elapsed,
            ))

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"SPOTIFY PLAYLIST ERROR: {e}", exc_info=True)
            try:
                _err = await get_emoji_async("ERROR")
                await _safe_edit(
                    progress_msg,
                    f"{_err} Unable to process this link.\n\nPlease try again.",
                    parse_mode="HTML",
                )
            except Exception:
                try:
                    _err = await get_emoji_async("ERROR")
                    await m.answer(
                        f"{_err} Unable to process this link.\n\nPlease try again.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
