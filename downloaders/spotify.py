"""
Spotify Downloader — Single track + Large playlist (600–700 songs).

Single track:
  - Works in private + group chats
  - Immediate status message
  - Send audio, delete status, reply ✓ Delivered

Playlist (group-only):
  - NO full pre-scan
  - Paginated streaming: spotdl --threads 2
  - Watch output dir for new MP3s, send each to DM immediately
  - Update GC progress every 5 tracks
  - Never abort on single track failure
  - Retry failed track once
  - Fix 95% freeze:
      * subprocess fully awaited
      * file handles closed before send
      * Redis updates non-blocking (fire-and-forget)
  - Concurrency: 2 simultaneous playlists max

Progress format (GC, monospace):
  ╔══════════════════════════════╗
  ║  Playlist: NAME              ║
  ╠══════════════════════════════╣
  ║  [▓▓▓▓░░░░░░]  40%           ║
  ║  280 / 700  completed        ║
  ╚══════════════════════════════╝
"""
import asyncio
import os
import re
import time
import tempfile
from pathlib import Path
from typing import Set, Tuple

from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError

from core.bot import bot
from core.config import config
from workers.task_queue import spotify_semaphore
from ui.formatting import (
    format_playlist_progress, format_playlist_final,
    format_playlist_dm_complete, mention, mono,
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
    return "/track/" in url_lower or url_lower.startswith("spotify:track:")

def is_spotify_url(url: str) -> bool:
    return "spotify.com" in url.lower() or url.lower().startswith("spotify:")

# ─── Single track ─────────────────────────────────────────────────────────────

async def handle_spotify_single(m: Message, url: str):
    """
    Download single Spotify track.
    Works in private + group chats.
    """
    if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
        await m.reply(mono("  ✗  Spotify API not configured"))
        return

    status = await m.reply(mono("  ⬇  Processing your track..."))

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            cmd = [
                "spotdl", "download", url,
                "--client-id", config.SPOTIFY_CLIENT_ID,
                "--client-secret", config.SPOTIFY_CLIENT_SECRET,
                "--output", str(tmp),
                "--format", "mp3",
                "--bitrate", "320k",
                "--threads", "1",
                "--no-cache",
            ]

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
                try:
                    proc.kill()
                    await asyncio.wait_for(proc.communicate(), timeout=5)
                except Exception:
                    pass
                try:
                    await status.edit_text(mono("  ✗  Download timed out"))
                except Exception:
                    pass
                return

            # Ensure process fully done
            if proc.returncode is None:
                try:
                    proc.kill()
                    await asyncio.wait_for(proc.communicate(), timeout=5)
                except Exception:
                    pass

            mp3_files = sorted(tmp.glob("*.mp3"))

            if not mp3_files:
                logger.warning(f"SPOTIFY SINGLE: No MP3. stderr={stderr.decode()[:200]}")
                try:
                    await status.edit_text(mono("  ✗  Could not process this link"))
                except Exception:
                    pass
                return

            mp3_file = mp3_files[0]
            artist, title = extract_song_metadata(mp3_file.stem)

            # Delete status before sending
            try:
                await status.delete()
            except Exception:
                pass

            # Send audio
            await bot.send_audio(
                m.chat.id,
                FSInputFile(mp3_file),
                title=title,
                performer=artist,
            )

            # Confirmation
            await m.reply(mono("  ✓  Delivered"))
            logger.info(f"SPOTIFY SINGLE: '{title}' by '{artist}' → {m.from_user.id}")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"SPOTIFY SINGLE ERROR: {e}")
        try:
            await status.edit_text(mono("  ✗  Could not process this link"))
        except Exception:
            pass

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
            raise  # Re-raise — user blocked bot
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
        # Scan for new MP3 files
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

            # Brief wait to ensure file fully written
            await asyncio.sleep(0.5)

            # Ensure file handle is closed (check size stable)
            try:
                size1 = fpath.stat().st_size
                await asyncio.sleep(0.3)
                size2 = fpath.stat().st_size
                if size1 != size2:
                    await asyncio.sleep(0.5)  # Still writing
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

            # Delete file immediately to free disk
            try:
                fpath.unlink(missing_ok=True)
            except Exception:
                pass

            # Update GC progress (non-blocking)
            total_done = sent_count + failed_count
            if total_done - last_progress_update >= PROGRESS_INTERVAL:
                last_progress_update = total_done
                display_total = max(total_hint, total_done)
                asyncio.create_task(_safe_edit(
                    progress_msg,
                    format_playlist_progress(playlist_name, total_done, display_total),
                ))

        # Check if process finished
        if proc.returncode is not None:
            # Final scan
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


async def _safe_edit(msg: Message, text: str):
    """Non-blocking safe message edit"""
    try:
        await msg.edit_text(text, parse_mode="HTML")
    except Exception:
        pass

# ─── Main playlist handler ────────────────────────────────────────────────────

async def handle_spotify_playlist(m: Message, url: str):
    """
    Route Spotify URL:
    - Single track → handle_spotify_single
    - Playlist/album → streaming group download
    """
    if is_spotify_track(url):
        await handle_spotify_single(m, url)
        return

    # Playlists: group-only
    if m.chat.type == "private":
        await m.reply(mono("  ✗  Spotify playlists only work in groups"))
        return

    logger.info(f"SPOTIFY PLAYLIST: Group request from {m.from_user.id}")

    # Cooldown check
    is_cooldown, minutes_left = await user_state_manager.is_on_cooldown(m.from_user.id)
    if is_cooldown:
        await m.reply(mono(f"  ⏳  Cooldown active — {minutes_left} min remaining"))
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
        await m.reply(
            mono("  ⚠  Start the bot first to receive songs in DM") +
            "\n\nTap below, then resend the playlist link 👇",
            reply_markup=keyboard,
        )
        return

    # Blocked check
    if await user_state_manager.has_blocked_bot(m.from_user.id):
        await m.reply(mono("  🚫  You have blocked the bot — unblock and try again"))
        return

    if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
        await m.reply(mono("  ✗  Spotify API not configured"))
        return

    async with spotify_semaphore:
        # Delete user's link after 4 seconds
        async def _delete_link():
            await asyncio.sleep(4)
            try:
                await m.delete()
            except Exception:
                pass
        asyncio.create_task(_delete_link())

        # Initial progress message
        progress_msg = await m.answer(
            format_playlist_progress("Loading...", 0, 0),
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
                    "--bitrate", "320k",
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
                            # "Found X songs in playlist NAME"
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
                                ))
                            # "Fetching X songs"
                            m3 = re.search(r"Fetching (\d+) songs?", text, re.IGNORECASE)
                            if m3 and total_hint == 0:
                                total_hint = int(m3.group(1))
                    except Exception:
                        pass

                stdout_task = asyncio.create_task(_read_stdout())

                # Stream-watch and send
                sent_count, failed_count, blocked = await _watch_and_send(
                    tmp, proc, m, progress_msg, playlist_name, total_hint
                )

                # Cancel stdout reader
                stdout_task.cancel()
                try:
                    await asyncio.wait_for(stdout_task, timeout=3)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

                # Ensure process fully done
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
                    try:
                        await progress_msg.edit_text(
                            mono("  🚫  Blocked — cooldown applied"),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
                    return

                if total_songs == 0:
                    try:
                        await progress_msg.edit_text(
                            mono("  ✗  No songs downloaded from playlist"),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
                    return

                # Delete progress message
                try:
                    await progress_msg.delete()
                except Exception:
                    pass

                # GC final summary
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
                await progress_msg.edit_text(
                    mono("  ✗  Spotify download failed"),
                    parse_mode="HTML",
                )
            except Exception:
                try:
                    await m.answer(mono("  ✗  Spotify download failed"))
                except Exception:
                    pass
