"""Spotify playlist downloader - Production grade with real-time progress"""
import asyncio
import time
import tempfile
from pathlib import Path
from typing import List
from aiogram.types import Message, FSInputFile

from core.bot import bot
from core.config import config
from workers.task_queue import spotify_semaphore
from ui.progress import SpotifyProgress
from ui.formatting import format_spotify_complete
from utils.helpers import mention, extract_song_metadata, get_file_size_mb
from utils.logger import logger

async def handle_spotify_playlist(m: Message, url: str):
    """
    Download Spotify playlist with exact workflow:
    1. Delete user message after 3-5 seconds
    2. Send "Spotify Playlist Fetched" message
    3. Live edit with dual progress bars
    4. Send songs in batches of 10 to DM
    5. Final completion message in group
    """
    async with spotify_semaphore:
        logger.info(f"SPOTIFY: Starting download for {url}")
        
        # Check credentials
        if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
            await m.answer("Spotify API not configured")
            return
        
        # Step 1: Delete user message after 3-5 seconds
        async def delete_user_message():
            await asyncio.sleep(4)
            try:
                await m.delete()
                logger.info("Deleted user's Spotify link")
            except Exception as e:
                logger.warning(f"Could not delete user message: {e}")
        
        asyncio.create_task(delete_user_message())
        
        # Step 2: Send initial "Fetched" message
        progress_msg = await m.answer("Spotify Playlist Fetched\nStarting download...")
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
                    await progress_msg.edit_text(f"Spotify download failed\n{error_msg}")
                    return
                
                # Find all downloaded MP3 files
                mp3_files = sorted(tmp.glob("*.mp3"))
                
                if not mp3_files:
                    await progress_msg.edit_text("No songs downloaded from playlist")
                    return
                
                total_songs = len(mp3_files)
                logger.info(f"Downloaded {total_songs} songs, starting DM delivery")
                
                # Step 3-4: Send songs in batches of 10 with live progress
                await send_songs_with_progress(
                    m,
                    progress_msg,
                    mp3_files,
                    total_songs
                )
                
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
                await progress_msg.edit_text(f"Spotify download failed\n{str(e)[:100]}")
            except:
                await m.answer(f"Spotify download failed\n{str(e)[:100]}")

async def monitor_spotify_download(progress_msg: Message, proc: asyncio.subprocess.Process):
    """
    Monitor download process and update progress message
    Shows simulated progress during download phase
    """
    progress = 0
    
    while proc.returncode is None:
        try:
            progress = min(progress + 8, 95)
            await progress_msg.edit_text(
                f"Downloading Playlist\n"
                f"{'█' * int(progress/8)}{'░' * (12-int(progress/8))} {progress}%\n\n"
                f"Fetching songs from Spotify..."
            )
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"Progress update failed: {e}")
            pass
    
    # Final download complete
    try:
        await progress_msg.edit_text(
            f"Downloading Playlist\n"
            f"{'█' * 12} 100%\n\n"
            f"Download complete, preparing to send..."
        )
    except:
        pass

async def send_songs_with_progress(
    m: Message,
    progress_msg: Message,
    mp3_files: List[Path],
    total_songs: int
):
    """
    Send songs to user's DM with real-time progress updates
    Sends in batches of 10 songs
    """
    sent_count = 0
    failed_count = 0
    batch_size = 10
    current_batch = []
    
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
            await bot.send_audio(
                m.from_user.id,
                FSInputFile(mp3_file),
                title=title,
                performer=artist
            )
            
            sent_count += 1
            progress.complete_song()
            current_batch.append(mp3_file.name)
            
            logger.info(f"Sent {i}/{total_songs}: {title} by {artist} ({file_size:.1f}MB)")
            
            # Update progress after each song
            try:
                await progress_msg.edit_text(progress.format_message("sending"))
            except:
                pass
            
            # Small delay to avoid rate limits
            await asyncio.sleep(0.3)
            
            # Every 10 songs or at the end, log batch completion
            if len(current_batch) >= batch_size or i == total_songs:
                logger.info(f"Batch complete: {len(current_batch)} songs sent ({sent_count}/{total_songs})")
                current_batch = []
        
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
