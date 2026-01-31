"""Spotify playlist downloader - Group-only with user state tracking"""
import asyncio
import time
import tempfile
from pathlib import Path
from typing import List
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError

from core.bot import bot
from core.config import config
from workers.task_queue import spotify_semaphore
from ui.progress import SpotifyProgress
from ui.formatting import format_spotify_complete, mention, styled_text
from utils.helpers import extract_song_metadata, get_file_size_mb
from utils.logger import logger
from utils.user_state import user_state_manager

async def handle_spotify_playlist(m: Message, url: str):
    """
    Download Spotify playlist with strict workflow:
    - ONLY works in groups
    - User must have started bot
    - User must not have blocked bot
    - User must not be on cooldown
    - Delete user message after 3-5 seconds
    - Live dual progress bars
    - Send songs to DM
    """
    
    # CRITICAL: Only allow in groups
    if m.chat.type == "private":
        await m.answer(f"❌ {styled_text('Spotify playlists only work in groups')}")
        return
    
    logger.info(f"SPOTIFY: Group request from user {m.from_user.id}")
    
    # Check if user is on cooldown
    is_cooldown, minutes_left = await user_state_manager.is_on_cooldown(m.from_user.id)
    if is_cooldown:
        await m.answer(
            f"⏳ {styled_text('You are temporarily blocked for abusing downloads')}\n"
            f"{styled_text('Try again after')} {minutes_left} {styled_text('minutes')}"
        )
        return
    
    # Check if user has started bot
    has_started = await user_state_manager.has_started_bot(m.from_user.id)
    
    if not has_started:
        # User hasn't started bot - send registration message
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"🎧 {styled_text('Start Downloader Bot')}",
                url=f"https://t.me/{(await bot.get_me()).username}?start=spotify"
            )]
        ])
        
        await m.answer(
            f"⚠️ {styled_text('You are not registered to receive downloads in DM')}\n\n"
            f"{styled_text('Start the bot first')} 👇",
            reply_markup=keyboard
        )
        return
    
    # Check if user has blocked bot
    has_blocked = await user_state_manager.has_blocked_bot(m.from_user.id)
    
    if has_blocked:
        await m.answer(
            f"🚫 {styled_text('You have blocked the bot')}\n\n"
            f"{styled_text('Unblock it and send the playlist again to continue')}"
        )
        return
    
    # All checks passed - proceed with download
    async with spotify_semaphore:
        # Step 1: Delete user message after 3-5 seconds
        async def delete_user_message():
            await asyncio.sleep(4)
            try:
                await m.delete()
                logger.info("Deleted user's Spotify link")
            except Exception as e:
                logger.warning(f"Could not delete user message: {e}")
        
        asyncio.create_task(delete_user_message())
        
        # Check credentials
        if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
            await m.answer(f"❌ {styled_text('Spotify API not configured')}")
            return
        
        # Step 2: Send initial "Fetched" message
        progress_msg = await m.answer(
            f"🎧 {styled_text('Spotify Playlist Fetched')}\n"
            f"⏳ {styled_text('Starting download')}..."
        )
        start_time = time.perf_counter()
        
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)
                
                # Build spotdl command
                cmd = [
                    "spotdl",
                    "download",
                    url,
                    "--client-id", config.SPOTIFY_CLIENT_ID,
                    "--client-secret", config.SPOTIFY_CLIENT_SECRET,
                    "--output", str(tmp),
                    "--format", "mp3",
                    "--bitrate", "192k",
                    "--threads", "4",
                    "--print-errors"
                ]
                
                logger.info("Starting spotdl with 4 parallel threads")
                
                # Start download process
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                # Monitor download with simulated progress
                download_task = asyncio.create_task(
                    monitor_spotify_download(progress_msg, proc)
                )
                
                # Wait for download to complete
                stdout, stderr = await proc.communicate()
                await download_task
                
                if proc.returncode != 0:
                    error_msg = stderr.decode()[:200]
                    logger.error(f"spotdl failed: {error_msg}")
                    await progress_msg.edit_text(
                        f"❌ {styled_text('Spotify download failed')}\n{error_msg}"
                    )
                    return
                
                # Find all downloaded MP3 files
                mp3_files = sorted(tmp.glob("*.mp3"))
                
                if not mp3_files:
                    await progress_msg.edit_text(
                        f"❌ {styled_text('No songs downloaded from playlist')}"
                    )
                    return
                
                total_songs = len(mp3_files)
                logger.info(f"Downloaded {total_songs} songs, starting DM delivery")
                
                # Step 3-4: Send songs with live progress
                success = await send_songs_with_progress(
                    m,
                    progress_msg,
                    mp3_files,
                    total_songs
                )
                
                if not success:
                    # User blocked bot during download - apply cooldown
                    await user_state_manager.mark_user_blocked(m.from_user.id)
                    await user_state_manager.apply_cooldown(m.from_user.id)
                    
                    try:
                        await progress_msg.edit_text(
                            f"🚫 {styled_text('You are temporarily blocked for abusing downloads')}\n"
                            f"{styled_text('Try again after 3 hours')}"
                        )
                    except:
                        pass
                    return
                
                elapsed = time.perf_counter() - start_time
                
                # Delete progress message
                try:
                    await progress_msg.delete()
                except:
                    pass
                
                # Step 5: Send final completion message in group
                completion_msg = format_spotify_complete(m.from_user, total_songs, total_songs)
                await m.answer(completion_msg, parse_mode="HTML")
                
                logger.info(f"SPOTIFY: Completed {total_songs} songs in {elapsed:.1f}s")
        
        except Exception as e:
            logger.error(f"SPOTIFY ERROR: {e}")
            try:
                await progress_msg.edit_text(
                    f"❌ {styled_text('Spotify download failed')}\n{str(e)[:100]}"
                )
            except:
                await m.answer(
                    f"❌ {styled_text('Spotify download failed')}\n{str(e)[:100]}"
                )

async def monitor_spotify_download(progress_msg: Message, proc: asyncio.subprocess.Process):
    """
    Monitor download process and update progress message
    Shows simulated progress during download phase
    """
    progress = 0
    
    while proc.returncode is None:
        try:
            progress = min(progress + 8, 95)
            filled = int(progress / 8)
            bar = '█' * filled + '░' * (12 - filled)
            
            await progress_msg.edit_text(
                f"📥 {styled_text('Downloading Playlist')}\n"
                f"{bar} {progress}%\n\n"
                f"⏳ {styled_text('Fetching songs from Spotify')}..."
            )
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"Progress update failed: {e}")
            pass
    
    # Final download complete
    try:
        await progress_msg.edit_text(
            f"📥 {styled_text('Downloading Playlist')}\n"
            f"{'█' * 12} 100%\n\n"
            f"✅ {styled_text('Download complete, preparing to send')}..."
        )
    except:
        pass

async def send_songs_with_progress(
    m: Message,
    progress_msg: Message,
    mp3_files: List[Path],
    total_songs: int
) -> bool:
    """
    Send songs to user's DM with real-time progress updates
    
    Returns:
        True if successful, False if user blocked bot
    """
    sent_count = 0
    failed_count = 0
    
    progress = SpotifyProgress(total_songs)
    
    for i, mp3_file in enumerate(mp3_files, 1):
        try:
            # Extract metadata
            artist, title = extract_song_metadata(mp3_file.stem)
            file_size = get_file_size_mb(str(mp3_file))
            
            # Update progress with current song
            progress.set_current_song(title, artist)
            progress.update_song_progress(0)
            
            # Update progress message
            try:
                await progress_msg.edit_text(progress.format_message("downloading"))
            except:
                pass
            
            # Simulate song download progress
            for prog in [30, 60, 90]:
                progress.update_song_progress(prog)
                try:
                    await progress_msg.edit_text(progress.format_message("downloading"))
                except:
                    pass
                await asyncio.sleep(0.1)
            
            # Send to DM
            try:
                await bot.send_audio(
                    m.from_user.id,
                    FSInputFile(mp3_file),
                    title=title,
                    performer=artist
                )
                
                sent_count += 1
                progress.complete_song()
                
                logger.info(f"Sent {i}/{total_songs}: {title} by {artist} ({file_size:.1f}MB)")
                
                # Update progress after each song
                try:
                    await progress_msg.edit_text(progress.format_message("sending"))
                except:
                    pass
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.3)
            
            except TelegramForbiddenError:
                # User blocked bot during download
                logger.error(f"User {m.from_user.id} blocked bot during Spotify download")
                return False
        
        except Exception as e:
            logger.error(f"Failed to send {mp3_file.name}: {e}")
            failed_count += 1
            progress.complete_song()
    
    # Final update
    try:
        await progress_msg.edit_text(progress.format_message("complete"))
    except:
        pass
    
    logger.info(f"Spotify delivery complete: {sent_count} sent, {failed_count} failed")
    return True
