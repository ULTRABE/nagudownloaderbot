"""
Spotify downloader — streaming playlist (group-only, DM delivery) + single track.

Playlist design:
  - NO full pre-scan before starting
  - spotdl downloads one-by-one with --threads 1
  - We watch the output directory for new files and send each as it appears
  - Progress bar updates every 3–5 tracks (avoids Telegram rate limits)
  - Handles 600–700 track playlists without memory pressure
  - Each file deleted from disk immediately after sending

Single track:
  - Works in private and group chats
  - 4–8 second target delivery
  - Proper URL detection (track vs playlist/album)
"""
import asyncio
import os
import time
import tempfile
from pathlib import Path
from typing import List, Optional, Set

from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError

from core.bot import bot
from core.config import config
from workers.task_queue import spotify_semaphore
from ui.formatting import format_spotify_complete, mention, styled_text
from utils.helpers import extract_song_metadata, get_file_size_mb
from utils.logger import logger
from utils.user_state import user_state_manager

# ─── URL type detection ───────────────────────────────────────────────────────

def is_spotify_playlist(url: str) -> bool:
    """Detect Spotify playlist or album URL"""
    url_lower = url.lower()
    return "/playlist/" in url_lower or "/album/" in url_lower

def is_spotify_track(url: str) -> bool:
    """Detect Spotify single track URL"""
    # Handle both open.spotify.com/track/... and spotify:track:...
    url_lower = url.lower()
    return "/track/" in url_lower or url_lower.startswith("spotify:track:")

def is_spotify_url(url: str) -> bool:
    """Detect any Spotify URL"""
    return "spotify.com" in url.lower() or url.lower().startswith("spotify:")

# ─── Progress bar helper ──────────────────────────────────────────────────────

def _make_progress_bar(done: int, total: int, width: int = 10) -> str:
    """Build a monospace progress bar string"""
    if total <= 0:
        pct = 0
    else:
        pct = min(100, int(done * 100 / total))
    filled = int(width * pct / 100)
    bar = "▓" * filled + "░" * (width - filled)
    return f"[{bar}] {pct}%"

def _progress_text(playlist_name: str, done: int, total: int) -> str:
    """Format GC progress message"""
    bar = _make_progress_bar(done, total)
    return (
        f"<code>Playlist: {playlist_name}</code>\n"
        f"<code>{bar}</code>\n"
        f"<code>{done}/{total} downloaded</code>"
    )

# ─── Single track handler ─────────────────────────────────────────────────────

async def handle_spotify_single(m: Message, url: str):
    """
    Download a single Spotify track.
    Works in both private and group chats.
    Target: 4–8 second delivery.
    """
    # Delete user's link message after 4 seconds (fire-and-forget)
    async def _delete_link():
        await asyncio.sleep(4)
        try:
            await m.delete()
        except Exception:
            pass
    asyncio.create_task(_delete_link())

    if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
        await m.answer("❌ Spotify API not configured.")
        return

    status_msg = await m.answer("🎧 Processing your track...")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            cmd = [
                "spotdl",
                "download",
                url,
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
                    await proc.communicate()
                except Exception:
                    pass
                await status_msg.edit_text("Could not process this link.")
                return

            # Ensure process is fully done
            if proc.returncode is None:
                try:
                    proc.kill()
                    await proc.communicate()
                except Exception:
                    pass

            mp3_files = sorted(tmp.glob("*.mp3"))

            if not mp3_files:
                logger.warning(f"SPOTIFY SINGLE: No MP3 found. stderr={stderr.decode()[:200]}")
                await status_msg.edit_text("Could not process this link.")
                return

            mp3_file = mp3_files[0]
            artist, title = extract_song_metadata(mp3_file.stem)

            # Delete status message before sending audio
            try:
                await status_msg.delete()
            except Exception:
                pass

            # Send audio WITHOUT caption
            await bot.send_audio(
                m.chat.id,
                FSInputFile(mp3_file),
                title=title,
                performer=artist,
            )

            # Confirmation mentioning user
            await m.answer(
                f"{mention(m.from_user)} — {styled_text('Track delivered')} ✅",
                parse_mode="HTML",
            )

            logger.info(f"SPOTIFY SINGLE: Sent '{title}' by '{artist}' to {m.from_user.id}")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"SPOTIFY SINGLE ERROR: {e}")
        try:
            await status_msg.edit_text("Could not process this link.")
        except Exception:
            pass

# ─── Playlist streaming watcher ───────────────────────────────────────────────

async def _watch_and_send(
    tmp: Path,
    proc: asyncio.subprocess.Process,
    m: Message,
    progress_msg: Message,
    playlist_name: str,
    total_hint: int,
) -> tuple:
    """
    Watch tmp directory for new MP3 files while spotdl runs.
    Send each file to user's DM as soon as it appears.
    Delete file from disk after sending to free memory.

    Returns (sent_count, failed_count, blocked).
    """
    sent_count = 0
    failed_count = 0
    seen: Set[str] = set()
    last_progress_update = 0
    PROGRESS_INTERVAL = 3  # update GC progress every N tracks

    while True:
        # Scan for new MP3 files
        try:
            current_files = {
                f.name: f
                for f in tmp.glob("*.mp3")
                if f.name not in seen
            }
        except Exception:
            current_files = {}

        for fname, fpath in current_files.items():
            seen.add(fname)

            # Wait briefly to ensure file is fully written
            await asyncio.sleep(0.3)

            try:
                artist, title = extract_song_metadata(fpath.stem)

                await bot.send_audio(
                    m.from_user.id,
                    FSInputFile(fpath),
                    title=title,
                    performer=artist,
                )
                sent_count += 1
                logger.info(f"SPOTIFY PLAYLIST: Sent {sent_count}: '{title}' by '{artist}'")

                # Delete file immediately after sending
                try:
                    fpath.unlink(missing_ok=True)
                except Exception:
                    pass

            except TelegramForbiddenError:
                logger.error(f"User {m.from_user.id} blocked bot during playlist download")
                # Kill the download process
                try:
                    proc.kill()
                except Exception:
                    pass
                return sent_count, failed_count, True

            except Exception as e:
                logger.error(f"SPOTIFY PLAYLIST: Failed to send '{fname}': {e}")
                failed_count += 1
                # Still delete to free disk space
                try:
                    fpath.unlink(missing_ok=True)
                except Exception:
                    pass

            # Update GC progress bar every N tracks
            total_done = sent_count + failed_count
            if total_done - last_progress_update >= PROGRESS_INTERVAL:
                last_progress_update = total_done
                try:
                    display_total = max(total_hint, total_done)
                    await progress_msg.edit_text(
                        _progress_text(playlist_name, total_done, display_total),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

        # Check if process finished
        if proc.returncode is not None:
            # Do one final scan for any remaining files
            await asyncio.sleep(0.5)
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
                try:
                    artist, title = extract_song_metadata(fpath.stem)
                    await bot.send_audio(
                        m.from_user.id,
                        FSInputFile(fpath),
                        title=title,
                        performer=artist,
                    )
                    sent_count += 1
                    try:
                        fpath.unlink(missing_ok=True)
                    except Exception:
                        pass
                except TelegramForbiddenError:
                    return sent_count, failed_count, True
                except Exception as e:
                    logger.error(f"SPOTIFY PLAYLIST: Final scan send failed '{fname}': {e}")
                    failed_count += 1
                    try:
                        fpath.unlink(missing_ok=True)
                    except Exception:
                        pass
            break

        # Poll every 1 second
        await asyncio.sleep(1.0)

    return sent_count, failed_count, False

# ─── Playlist name extractor ──────────────────────────────────────────────────

async def _get_playlist_name(url: str) -> str:
    """
    Try to extract playlist name quickly using spotdl --print-errors.
    Falls back to 'Playlist' if it takes too long.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "spotdl",
            "save",
            url,
            "--save-file", "/dev/null",
            "--client-id", config.SPOTIFY_CLIENT_ID,
            "--client-secret", config.SPOTIFY_CLIENT_SECRET,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            output = stdout.decode() + stderr.decode()
            # spotdl prints "Fetching X songs from playlist: NAME"
            import re
            m = re.search(r"playlist[:\s]+(.+?)(?:\n|$)", output, re.IGNORECASE)
            if m:
                return m.group(1).strip()[:40]
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.communicate()
            except Exception:
                pass
    except Exception:
        pass
    return "Playlist"

# ─── Main playlist handler ────────────────────────────────────────────────────

async def handle_spotify_playlist(m: Message, url: str):
    """
    Download Spotify playlist with streaming flow:
    - Route single tracks to handle_spotify_single
    - Group-only for playlists/albums
    - Start downloading immediately (no full pre-scan)
    - Send each track to DM as it finishes
    - Update GC progress bar every 3–5 tracks
    - Handle 600–700 tracks without memory pressure
    """
    # Route single tracks
    if is_spotify_track(url):
        await handle_spotify_single(m, url)
        return

    # Playlists/albums: group-only
    if m.chat.type == "private":
        await m.answer(f"❌ {styled_text('Spotify playlists only work in groups')}")
        return

    logger.info(f"SPOTIFY PLAYLIST: Group request from user {m.from_user.id}")

    # Cooldown check
    is_cooldown, minutes_left = await user_state_manager.is_on_cooldown(m.from_user.id)
    if is_cooldown:
        await m.answer(
            f"⏳ {styled_text('You are temporarily blocked for abusing downloads')}\n"
            f"{styled_text('Try again after')} {minutes_left} {styled_text('minutes')}"
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
        await m.answer(
            f"⚠️ {styled_text('You need to start the bot first to receive songs in DM')}\n\n"
            f"{styled_text('Tap the button below, then resend the playlist link')} 👇",
            reply_markup=keyboard,
        )
        return

    # Blocked check
    has_blocked = await user_state_manager.has_blocked_bot(m.from_user.id)
    if has_blocked:
        await m.answer(
            f"🚫 {styled_text('You have blocked the bot')}\n\n"
            f"{styled_text('Unblock it and send the playlist again')}"
        )
        return

    # Credentials check
    if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
        await m.answer(f"❌ {styled_text('Spotify API not configured')}")
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

        # Show initial progress message immediately
        progress_msg = await m.answer(
            f"<code>Playlist: Loading...</code>\n"
            f"<code>[░░░░░░░░░░] 0%</code>\n"
            f"<code>Starting download...</code>",
            parse_mode="HTML",
        )

        start_time = time.perf_counter()

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)

                # Build spotdl command — threads=1 for streaming (one file at a time)
                # --no-cache avoids stale data issues
                cmd = [
                    "spotdl",
                    "download",
                    url,
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

                # Parse playlist name from spotdl output in background
                playlist_name = "Playlist"
                total_hint = 0

                async def _read_stdout():
                    nonlocal playlist_name, total_hint
                    import re
                    try:
                        async for line in proc.stdout:
                            text = line.decode(errors="replace").strip()
                            if not text:
                                continue
                            # "Found X songs in playlist NAME"
                            m2 = re.search(r"Found (\d+) songs? in .+?[:\s]+(.+?)$", text, re.IGNORECASE)
                            if m2:
                                total_hint = int(m2.group(1))
                                playlist_name = m2.group(2).strip()[:40]
                                try:
                                    await progress_msg.edit_text(
                                        _progress_text(playlist_name, 0, total_hint),
                                        parse_mode="HTML",
                                    )
                                except Exception:
                                    pass
                            # Also try "Fetching X songs"
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

                # Ensure stdout reader finishes
                stdout_task.cancel()
                try:
                    await stdout_task
                except asyncio.CancelledError:
                    pass

                # Ensure process is fully done
                if proc.returncode is None:
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=10)
                    except asyncio.TimeoutError:
                        try:
                            proc.kill()
                            await proc.communicate()
                        except Exception:
                            pass

                elapsed = time.perf_counter() - start_time
                total_songs = sent_count + failed_count

                if blocked:
                    await user_state_manager.mark_user_blocked(m.from_user.id)
                    await user_state_manager.apply_cooldown(m.from_user.id)
                    try:
                        await progress_msg.edit_text(
                            f"🚫 {styled_text('You are temporarily blocked for abusing downloads')}\n"
                            f"{styled_text('Try again after 1 hour')}"
                        )
                    except Exception:
                        pass
                    return

                if total_songs == 0:
                    await progress_msg.edit_text(
                        f"❌ {styled_text('No songs downloaded from playlist')}"
                    )
                    return

                # Delete progress message
                try:
                    await progress_msg.delete()
                except Exception:
                    pass

                # GC completion summary
                gc_summary = (
                    f"{mention(m.from_user)}\n\n"
                    f"<code>Playlist Completed</code>\n"
                    f"<code>Total:  {total_songs}</code>\n"
                    f"<code>Sent:   {sent_count}</code>\n"
                    f"<code>Failed: {failed_count}</code>"
                )
                await m.answer(gc_summary, parse_mode="HTML")

                # DM completion message
                try:
                    await bot.send_message(
                        m.from_user.id,
                        f"<code>Playlist: {playlist_name}</code>\n"
                        f"<code>Status: Completed ✅</code>\n\n"
                        f"Thank you for using <b>IDIRECTNango Downloader Bot</b>.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

                logger.info(
                    f"SPOTIFY PLAYLIST: Done — {sent_count} sent, {failed_count} failed "
                    f"in {elapsed:.1f}s"
                )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"SPOTIFY PLAYLIST ERROR: {e}", exc_info=True)
            try:
                await progress_msg.edit_text(
                    f"❌ {styled_text('Spotify download failed')}\n{str(e)[:100]}"
                )
            except Exception:
                try:
                    await m.answer(f"❌ {styled_text('Spotify download failed')}")
                except Exception:
                    pass
