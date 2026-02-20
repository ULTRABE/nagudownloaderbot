"""
Spotify Downloader — Single track + Large playlist (600–700 songs).

Single track (group):
  🎵 Processing Track... → 📥 Downloading... [progress] → audio to DM → ✓ Sent to your DM

Single track (DM):
  🎵 Processing Track... → 📥 Downloading... [progress] → audio → ✓ Delivered — <mention>

Playlist (group-only):
  🎵 Playlist Detected → Starting download...
  Progress: Playlist: {name} [██░░░░] 60% / 420 / 700 completed
  Final: 🎉 Playlist Completed — mention
  DM: 🎵 Playlist Delivered

URL detection:
  https://open.spotify.com/track/
  https://open.spotify.com/playlist/
  https://open.spotify.com/album/
  spotify:track:
"""
import asyncio
import os
import re
import time
import tempfile
import traceback
from pathlib import Path
from typing import Set, Tuple, Optional

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

# ─── Progress bar helper ──────────────────────────────────────────────────────

def _progress_bar(pct: int, label: str = "") -> str:
    width = 10
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    text = f"📥 <b>Downloading</b>\n\n[{bar}] {pct}%"
    if label:
        text += f"\n{label}"
    return text

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

# ─── Single track ─────────────────────────────────────────────────────────────

async def handle_spotify_single(m: Message, url: str):
    """
    Download single Spotify track.
    Works in private + group chats.

    Group: 🎵 Processing Track... → 📥 Downloading... → audio to DM → ✓ Sent to your DM
    DM:    🎵 Processing Track... → 📥 Downloading... → audio → ✓ Delivered — <mention>

    Uses 192k bitrate for speed.
    Total target: < 5 seconds.
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

    status = await _safe_reply(m, "🎵 Processing Track...", parse_mode="HTML")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            # Animate progress while downloading
            async def _animate():
                steps = [
                    (20, "Fetching audio..."),
                    (40, "Fetching audio..."),
                    (60, "Encoding..."),
                    (80, "Encoding..."),
                ]
                for pct, label in steps:
                    await asyncio.sleep(1.5)
                    await _safe_edit(status, _progress_bar(pct, label), parse_mode="HTML")

            anim_task = asyncio.create_task(_animate())

            cmd = [
                "spotdl", "download", url,
                "--client-id", config.SPOTIFY_CLIENT_ID,
                "--client-secret", config.SPOTIFY_CLIENT_SECRET,
                "--output", str(tmp),
                "--format", "mp3",
                "--bitrate", "192k",   # 192k is fast enough, 320k is too slow
                "--threads", "2",
                "--no-cache",
            ]

            logger.info(f"SPOTIFY SINGLE: Starting download for {url}")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=config.DOWNLOAD_TIMEOUT,
                )
            except asyncio.TimeoutError:
                anim_task.cancel()
                try:
                    proc.kill()
                    await asyncio.wait_for(proc.communicate(), timeout=5)
                except Exception:
                    pass
                await _safe_delete(status)
                await _safe_reply(
                    m,
                    "⚠ Unable to process this link.\n\nPlease try again.",
                    parse_mode="HTML",
                )
                return

            anim_task.cancel()

            if proc.returncode is None:
                try:
                    proc.kill()
                    await asyncio.wait_for(proc.communicate(), timeout=5)
                except Exception:
                    pass

            mp3_files = sorted(tmp.glob("*.mp3"))

            if not mp3_files:
                stderr_text = stderr.decode(errors="replace")[:500] if stderr else ""
                logger.warning(f"SPOTIFY SINGLE: No MP3 found. returncode={proc.returncode}, stderr={stderr_text}")
                await _safe_delete(status)
                await _safe_reply(
                    m,
                    "⚠ Unable to process this link.\n\nPlease try again.",
                    parse_mode="HTML",
                )
                return

            mp3_file = mp3_files[0]
            artist, title = extract_song_metadata(mp3_file.stem)

            logger.info(f"SPOTIFY SINGLE: Downloaded '{title}' by '{artist}'")

            await _safe_delete(status)

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
                    # User hasn't started bot
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
        await _safe_delete(status)
        await _safe_reply(
            m,
            "⚠ Unable to process this link.\n\nPlease try again.",
            parse_mode="HTML",
        )

# ─── Playlist watcher ─────────────────────────────────────────────────────────

async def _send_mp3_to_dm(
    user_id: int,
    fpath: Path,
    retry: bool = True,
) -> bool:
    """
    Send one MP3 to user DM.
    Returns True on success.
    Retries once on failure (except blocked).
    """
    artist, title = extract_song_metadata(fpath.stem)
    for attempt in range(2 if retry else 1):
        try:
            await bot.send_audio(
                user_id,
                FSInputFile(fpath),
                title=title,
                performer=artist,
            )
            return True
        except TelegramForbiddenError:
            raise
        except Exception as e:
            if attempt == 0:
                logger.debug(f"Send retry for '{fpath.name}': {e}")
                await asyncio.sleep(1)
            else:
                logger.error(f"Send failed for '{fpath.name}': {e}")
    return False


async def _watch_and_send(
    tmp: Path,
    proc: asyncio.subprocess.Process,
    m: Message,
    progress_msg: Message,
    playlist_name: str,
    total_hint: int,
) -> Tuple[int, int, bool]:
    """
    Watch tmp dir for new MP3s while spotdl runs.
    Send each to user DM immediately.
    Update GC progress every 5 tracks.
    Returns (sent_count, failed_count, blocked).
    """
    sent_count = 0
    failed_count = 0
    seen: Set[str] = set()
    last_progress_update = 0
    PROGRESS_INTERVAL = 5

    while True:
        try:
            new_files = {
                f.name: f
                for f in tmp.glob("*.mp3")
                if f.name not in seen
            }
        except Exception:
            new_files = {}

        for fname, fpath in new_files.items():
            seen.add(fname)

            await asyncio.sleep(0.5)

            try:
                size1 = fpath.stat().st_size
                await asyncio.sleep(0.3)
                size2 = fpath.stat().st_size
                if size1 != size2:
                    await asyncio.sleep(0.5)
            except Exception:
                pass

            try:
                ok = await _send_mp3_to_dm(m.from_user.id, fpath)
                if ok:
                    sent_count += 1
                    logger.info(f"SPOTIFY PLAYLIST: Sent {sent_count}: '{fname}'")
                else:
                    failed_count += 1
            except TelegramForbiddenError:
                logger.error(f"User {m.from_user.id} blocked bot")
                try:
                    proc.kill()
                except Exception:
                    pass
                return sent_count, failed_count, True
            except Exception as e:
                logger.error(f"SPOTIFY PLAYLIST: Failed '{fname}': {e}")
                failed_count += 1

            try:
                fpath.unlink(missing_ok=True)
            except Exception:
                pass

            total_done = sent_count + failed_count
            if total_done - last_progress_update >= PROGRESS_INTERVAL:
                last_progress_update = total_done
                display_total = max(total_hint, total_done)
                asyncio.create_task(_safe_edit(
                    progress_msg,
                    format_playlist_progress(playlist_name, total_done, display_total),
                    parse_mode="HTML",
                ))

        if proc.returncode is not None:
            await asyncio.sleep(1.0)
            try:
                final_files = {
                    f.name: f
                    for f in tmp.glob("*.mp3")
                    if f.name not in seen
                }
            except Exception:
                final_files = {}

            for fname, fpath in final_files.items():
                seen.add(fname)
                await asyncio.sleep(0.3)
                try:
                    ok = await _send_mp3_to_dm(m.from_user.id, fpath)
                    if ok:
                        sent_count += 1
                    else:
                        failed_count += 1
                except TelegramForbiddenError:
                    return sent_count, failed_count, True
                except Exception as e:
                    logger.error(f"SPOTIFY PLAYLIST: Final scan failed '{fname}': {e}")
                    failed_count += 1
                try:
                    fpath.unlink(missing_ok=True)
                except Exception:
                    pass
            break

        await asyncio.sleep(1.0)

    return sent_count, failed_count, False

# ─── Main playlist handler ────────────────────────────────────────────────────

async def handle_spotify_playlist(m: Message, url: str):
    """
    Route Spotify URL:
    - Single track → handle_spotify_single
    - Playlist/album → streaming group download

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
    Inner playlist download — wrapped separately for clean error handling.
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

        # Initial message
        progress_msg = await m.answer(
            "🎵 <b>Playlist Detected</b>\n\nStarting download...",
            parse_mode="HTML",
        )

        start_time = time.perf_counter()

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)

                cmd = [
                    "spotdl", "download", url,
                    "--client-id", config.SPOTIFY_CLIENT_ID,
                    "--client-secret", config.SPOTIFY_CLIENT_SECRET,
                    "--output", str(tmp),
                    "--format", "mp3",
                    "--bitrate", "192k",   # 192k for speed
                    "--threads", "2",
                    "--no-cache",
                    "--print-errors",
                ]

                logger.info(f"SPOTIFY PLAYLIST: Starting spotdl for {url}")

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                playlist_name = "Playlist"
                total_hint = 0

                async def _read_stdout():
                    nonlocal playlist_name, total_hint
                    try:
                        async for line in proc.stdout:
                            text = line.decode(errors="replace").strip()
                            if not text:
                                continue
                            logger.debug(f"spotdl: {text}")
                            m2 = re.search(
                                r"Found (\d+) songs? in .+?[:\s]+(.+?)$",
                                text, re.IGNORECASE
                            )
                            if m2:
                                total_hint = int(m2.group(1))
                                playlist_name = m2.group(2).strip()[:40]
                                asyncio.create_task(_safe_edit(
                                    progress_msg,
                                    format_playlist_progress(playlist_name, 0, total_hint),
                                    parse_mode="HTML",
                                ))
                            m3 = re.search(r"Fetching (\d+) songs?", text, re.IGNORECASE)
                            if m3 and total_hint == 0:
                                total_hint = int(m3.group(1))
                    except Exception as e:
                        logger.debug(f"stdout reader error: {e}")

                stdout_task = asyncio.create_task(_read_stdout())

                sent_count, failed_count, blocked = await _watch_and_send(
                    tmp, proc, m, progress_msg, playlist_name, total_hint
                )

                stdout_task.cancel()
                try:
                    await asyncio.wait_for(stdout_task, timeout=3)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

                if proc.returncode is None:
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=10)
                    except asyncio.TimeoutError:
                        try:
                            proc.kill()
                            await asyncio.wait_for(proc.communicate(), timeout=5)
                        except Exception:
                            pass

                elapsed = time.perf_counter() - start_time
                total_songs = sent_count + failed_count

                if blocked:
                    await user_state_manager.mark_user_blocked(m.from_user.id)
                    await user_state_manager.apply_cooldown(m.from_user.id)
                    await _safe_edit(
                        progress_msg,
                        "🚫 Blocked — cooldown applied.",
                        parse_mode="HTML",
                    )
                    return

                if total_songs == 0:
                    logger.warning(f"SPOTIFY PLAYLIST: No songs sent. returncode={proc.returncode}")
                    await _safe_edit(
                        progress_msg,
                        "⚠ Unable to process this link.\n\nPlease try again.",
                        parse_mode="HTML",
                    )
                    return

                # Delete progress message
                await _safe_delete(progress_msg)

                # GC final summary — mention user
                await m.answer(
                    format_playlist_final(
                        m.from_user, playlist_name,
                        total_songs, sent_count, failed_count
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
