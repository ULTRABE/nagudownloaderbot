"""Instagram downloader - fully async"""
import asyncio
import time
import tempfile
from pathlib import Path
from yt_dlp import YoutubeDL
from aiogram.types import Message, FSInputFile

from core.bot import bot
from core.config import config
from workers.task_queue import download_semaphore
from ui.formatting import format_caption
from utils.logger import logger

async def ig_download(url: str, output_path: Path, use_cookies: bool = False):
    """Download Instagram video asynchronously"""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "best[height<=720][ext=mp4]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(output_path),
        "proxy": config.pick_proxy(),
        "http_headers": {"User-Agent": config.pick_user_agent()},
        "concurrent_fragment_downloads": 20,
        "http_chunk_size": 10485760,
    }
    
    if use_cookies and Path(config.IG_COOKIES).exists():
        opts["cookiefile"] = config.IG_COOKIES
        logger.info("Using Instagram cookies (fallback)")
    
    # Run yt-dlp in thread pool to avoid blocking
    await asyncio.to_thread(lambda: YoutubeDL(opts).download([url]))

async def ig_optimize(src: Path, out: Path):
    """Optimize Instagram video asynchronously"""
    size_mb = src.stat().st_size / 1024 / 1024
    logger.info(f"IG: {size_mb:.2f} MB")
    
    if size_mb <= 18:
        # Fast copy (no re-encode)
        logger.info("IG: Fast copy (<=18MB)")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", str(src), "-c", "copy", str(out),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
    else:
        # Fast VP9 compression
        logger.info("IG: Fast VP9 compression (>18MB)")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", str(src),
            "-vf", "scale=720:-2",
            "-c:v", "libvpx-vp9", "-crf", "26", "-b:v", "0",
            "-cpu-used", "8", "-row-mt", "1",
            "-pix_fmt", "yuv420p",
            "-c:a", "libopus", "-b:a", "48k",
            "-movflags", "+faststart",
            str(out),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()

async def handle_instagram(m: Message, url: str):
    """Handle Instagram download request"""
    async with download_semaphore:
        logger.info(f"IG: {url}")
        sticker = await bot.send_sticker(m.chat.id, config.IG_STICKER)
        start = time.perf_counter()

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)
                raw = tmp / "ig.mp4"
                final = tmp / "igf.mp4"

                # Try without cookies first
                try:
                    await ig_download(url, raw, use_cookies=False)
                except:
                    logger.info("IG: Retrying with cookies")
                    await ig_download(url, raw, use_cookies=True)

                # Optimize video
                await ig_optimize(raw, final)

                elapsed = time.perf_counter() - start
                
                # Delete sticker
                try:
                    await bot.delete_message(m.chat.id, sticker.message_id)
                except:
                    pass

                # Send video
                sent = await bot.send_video(
                    m.chat.id,
                    FSInputFile(final),
                    caption=format_caption(m.from_user, elapsed),
                    parse_mode="HTML",
                    supports_streaming=True
                )

                # Pin in groups
                if m.chat.type != "private":
                    try:
                        await bot.pin_chat_message(m.chat.id, sent.message_id)
                    except:
                        pass
                
                logger.info(f"IG: Done in {elapsed:.2f}s")
                
        except Exception as e:
            logger.error(f"IG: {e}")
            try:
                await bot.delete_message(m.chat.id, sticker.message_id)
            except:
                pass
            await m.answer(f"❌ 𝐈𝐧𝐬𝐭𝐚𝐠𝐫𝐚𝐦 𝐅𝐚𝐢𝐥𝐞𝐝\n{str(e)[:100]}")
