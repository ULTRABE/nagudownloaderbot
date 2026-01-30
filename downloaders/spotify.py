"""Spotify playlist downloader - with real-time progress UI and parallel processing"""
import asyncio
import time
import tempfile
import subprocess
from pathlib import Path
from aiogram.types import Message, FSInputFile

from core.bot import bot
from core.config import config
from workers.task_queue import spotify_semaphore
from ui.progress import create_progress_bar
from utils.helpers import mention
from utils.logger import logger

async def handle_spotify_playlist(m: Message, url: str):
    """Download Spotify playlist with real-time progress updates"""
    async with spotify_semaphore:
        logger.info(f"SPOTIFY: {url}")
        
        # Check if Spotify credentials are set
        if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
            await m.answer("❌ Spotify API not configured")
            return
        
        # Delete user message after 3-5 seconds
        async def delete_user_message():
            await asyncio.sleep(4)
            try:
                await m.delete()
                logger.info("Deleted user's Spotify link")
            except:
                pass
        
        asyncio.create_task(delete_user_message())
        
        # Phase 1: Initial message
        status_msg = await m.answer("🎵 Spotify playlist detected...\n⏳ Fetching playlist data...")
        start = time.perf_counter()
        
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)
                
                # Phase 2: Downloading
                await status_msg.edit_text("📥 Starting download...\n" + create_progress_bar(0, 100))
                
                # Use spotdl to download entire playlist
                cmd = [
                    "spotdl",
                    "download",
                    url,
                    "--client-id", config.SPOTIFY_CLIENT_ID,
                    "--client-secret", config.SPOTIFY_CLIENT_SECRET,
                    "--output", str(tmp),
                    "--format", "mp3",
                    "--bitrate", "192k",
                    "--threads", "4",  # Parallel downloads
                    "--print-errors",
                ]
                
                logger.info(f"Running spotdl download with 4 threads...")
                
                # Run spotdl asynchronously
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                # Monitor progress (simulate since spotdl doesn't provide real-time progress)
                progress_task = asyncio.create_task(
                    update_download_progress(status_msg, proc)
                )
                
                # Wait for download to complete
                stdout, stderr = await proc.communicate()
                await progress_task
                
                if proc.returncode != 0:
                    logger.error(f"spotdl failed: {stderr.decode()}")
                    await status_msg.edit_text(f"❌ Spotify Failed\n{stderr.decode()[:100]}")
                    return
                
                # Find all downloaded MP3 files
                mp3_files = list(tmp.glob("*.mp3"))
                
                if not mp3_files:
                    await status_msg.edit_text("❌ No songs downloaded")
                    return
                
                total = len(mp3_files)
                
                # Show download complete
                await status_msg.edit_text(
                    f"✅ Downloaded {total} songs!\n"
                    f"📤 Sending to your DM...\n\n"
                    f"{create_progress_bar(0, total)}"
                )
                
                sent = 0
                failed = 0
                
                # Send each song to DM with real-time progress updates
                for i, mp3 in enumerate(mp3_files, 1):
                    try:
                        # Extract artist and title from filename
                        filename = mp3.stem
                        if ' - ' in filename:
                            artist, title = filename.split(' - ', 1)
                        else:
                            artist = "Unknown Artist"
                            title = filename
                        
                        file_size = mp3.stat().st_size / 1024 / 1024
                        
                        # Send without caption to DM
                        await bot.send_audio(
                            m.from_user.id,
                            FSInputFile(mp3),
                            title=title,
                            performer=artist
                        )
                        sent += 1
                        logger.info(f"DM: {title} by {artist} ({file_size:.1f}MB)")
                        
                        # Update progress every song or every 3 songs for large playlists
                        update_interval = 1 if total <= 20 else 3
                        if i % update_interval == 0 or i == total:
                            try:
                                progress_text = f"""📤 Sending to DM...

{create_progress_bar(sent, total)}
{sent}/{total} songs sent

Now sending:
{title} - {artist}"""
                                await status_msg.edit_text(progress_text)
                            except:
                                pass
                        
                        # Small delay between sends to avoid rate limits
                        await asyncio.sleep(0.3)
                        
                    except Exception as e:
                        logger.error(f"Failed to send {mp3.name}: {e}")
                        failed += 1
            
                elapsed = time.perf_counter() - start
                
                # Delete progress message
                try:
                    await status_msg.delete()
                except:
                    pass
                
                # Send final summary in group
                await m.answer(
                    f"""✅ Spotify Playlist Complete!

{mention(m.from_user)}

📊 Summary:
• Total: {total} songs
• Sent: {sent} ✅
• Failed: {failed} ❌
• Time: {elapsed:.1f}s

All songs sent to your DM! 💌""",
                    parse_mode="HTML"
                )
                
                logger.info(f"SPOTIFY: {sent} songs in {elapsed:.2f}s")
            
        except Exception as e:
            logger.error(f"SPOTIFY: {e}")
            try:
                await status_msg.edit_text(f"❌ Spotify Failed\n{str(e)[:100]}")
            except:
                await m.answer(f"❌ Spotify Failed\n{str(e)[:100]}")

async def update_download_progress(status_msg: Message, proc: asyncio.subprocess.Process):
    """Update progress bar during download phase"""
    progress = 0
    while proc.returncode is None:
        try:
            # Simulate progress (since spotdl doesn't provide real-time progress)
            progress = min(progress + 5, 95)
            await status_msg.edit_text(
                f"📥 Downloading from Spotify...\n{create_progress_bar(progress, 100)}"
            )
            await asyncio.sleep(2)
        except:
            pass
    
    # Final update
    try:
        await status_msg.edit_text(
            f"✅ Download complete!\n{create_progress_bar(100, 100)}"
        )
    except:
        pass
