"""
Watchdog system — timeout protection, job state tracking, anti-stuck.
Prevents the bot from hanging on slow downloads or crashed FFmpeg processes.
"""
import asyncio
import time
import hashlib
from typing import Optional, Dict, Any
from utils.logger import logger
from utils.redis_client import redis_client

# ─── In-memory active job registry ───────────────────────────────────────────
# Maps job_id -> asyncio.Task so we can cancel hung jobs
_active_jobs: Dict[str, asyncio.Task] = {}

# ─── Job state helpers ────────────────────────────────────────────────────────

def _job_key(job_id: str) -> str:
    return f"job:state:{job_id}"

def make_job_id(user_id: int, url: str) -> str:
    """Deterministic job ID from user + URL"""
    raw = f"{user_id}:{url}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]

async def register_job(job_id: str, user_id: int, url: str, task: asyncio.Task):
    """Register a new download job"""
    _active_jobs[job_id] = task
    await redis_client.set(
        _job_key(job_id),
        f"running:{user_id}:{int(time.time())}",
        expire=600  # auto-expire after 10 min
    )
    logger.debug(f"Job registered: {job_id} for user {user_id}")

async def finish_job(job_id: str):
    """Mark job as finished and clean up"""
    _active_jobs.pop(job_id, None)
    await redis_client.delete(_job_key(job_id))
    logger.debug(f"Job finished: {job_id}")

async def cancel_user_jobs(user_id: int):
    """Cancel all active jobs for a user (when they send a new link)"""
    to_cancel = []
    for job_id, task in list(_active_jobs.items()):
        state = await redis_client.get(_job_key(job_id))
        if state and f":{user_id}:" in state:
            to_cancel.append((job_id, task))
    
    for job_id, task in to_cancel:
        if not task.done():
            task.cancel()
            logger.info(f"Cancelled previous job {job_id} for user {user_id}")
        await finish_job(job_id)

async def is_job_running(job_id: str) -> bool:
    """Check if a job is currently running"""
    return await redis_client.exists(_job_key(job_id))

# ─── URL deduplication ────────────────────────────────────────────────────────

def _dedup_key(user_id: int, url: str) -> str:
    h = hashlib.md5(f"{user_id}:{url}".encode()).hexdigest()[:16]
    return f"dedup:{h}"

async def mark_url_processing(user_id: int, url: str, ttl: int = 300) -> bool:
    """
    Mark URL as being processed.
    Returns True if this is a new request, False if duplicate.
    """
    key = _dedup_key(user_id, url)
    existing = await redis_client.exists(key)
    if existing:
        return False
    await redis_client.set(key, "1", expire=ttl)
    return True

async def clear_url_processing(user_id: int, url: str):
    """Clear URL processing lock"""
    key = _dedup_key(user_id, url)
    await redis_client.delete(key)

# ─── Timeout wrapper ──────────────────────────────────────────────────────────

async def with_timeout(coro, timeout_seconds: int, job_id: Optional[str] = None):
    """
    Run a coroutine with a timeout.
    Cancels and cleans up on timeout.
    Raises asyncio.TimeoutError if exceeded.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.warning(f"Job {job_id or 'unknown'} timed out after {timeout_seconds}s")
        if job_id:
            await finish_job(job_id)
        raise
    except asyncio.CancelledError:
        logger.info(f"Job {job_id or 'unknown'} was cancelled")
        if job_id:
            await finish_job(job_id)
        raise

# ─── Temp file cleanup ────────────────────────────────────────────────────────

async def cleanup_temp_dir(tmp_dir: str):
    """Async cleanup of temp directory"""
    import shutil
    import os
    try:
        if os.path.exists(tmp_dir):
            await asyncio.to_thread(shutil.rmtree, tmp_dir, ignore_errors=True)
    except Exception as e:
        logger.warning(f"Temp cleanup failed for {tmp_dir}: {e}")

# ─── Per-user concurrency tracker ────────────────────────────────────────────

_user_active_count: Dict[int, int] = {}
_user_lock = asyncio.Lock()

async def acquire_user_slot(user_id: int, max_slots: int = 2) -> bool:
    """
    Try to acquire a concurrency slot for a user.
    Returns True if slot acquired, False if user is at limit.
    """
    async with _user_lock:
        current = _user_active_count.get(user_id, 0)
        if current >= max_slots:
            return False
        _user_active_count[user_id] = current + 1
        return True

async def release_user_slot(user_id: int):
    """Release a concurrency slot for a user"""
    async with _user_lock:
        current = _user_active_count.get(user_id, 0)
        if current > 0:
            _user_active_count[user_id] = current - 1
        else:
            _user_active_count.pop(user_id, None)
