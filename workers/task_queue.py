"""Task queue and semaphore management"""
import asyncio
from typing import Callable, Any, Coroutine
from core.config import config
from utils.logger import logger

# Semaphores for concurrent task limiting
download_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_DOWNLOADS)
music_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_MUSIC)
spotify_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_SPOTIFY)

class TaskQueue:
    """
    Async task queue for managing background downloads
    """
    
    def __init__(self, max_workers: int = 10):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.max_workers = max_workers
        self.workers: list[asyncio.Task] = []
        self.running = False
    
    async def worker(self, worker_id: int):
        """Worker coroutine that processes tasks from queue"""
        logger.info(f"Worker {worker_id} started")
        
        while self.running:
            try:
                # Get task from queue with timeout
                task_func, args, kwargs = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=1.0
                )
                
                try:
                    # Execute task
                    if asyncio.iscoroutinefunction(task_func):
                        await task_func(*args, **kwargs)
                    else:
                        await asyncio.to_thread(task_func, *args, **kwargs)
                except Exception as e:
                    logger.error(f"Worker {worker_id} task failed: {e}")
                finally:
                    self.queue.task_done()
                    
            except asyncio.TimeoutError:
                # No task available, continue loop
                continue
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
        
        logger.info(f"Worker {worker_id} stopped")
    
    async def start(self):
        """Start worker pool"""
        if self.running:
            return
        
        self.running = True
        self.workers = [
            asyncio.create_task(self.worker(i))
            for i in range(self.max_workers)
        ]
        logger.info(f"Task queue started with {self.max_workers} workers")
    
    async def stop(self):
        """Stop worker pool"""
        self.running = False
        
        # Wait for all workers to finish
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
        
        logger.info("Task queue stopped")
    
    async def add_task(self, func: Callable, *args, **kwargs):
        """Add task to queue"""
        await self.queue.put((func, args, kwargs))
    
    def add_task_nowait(self, func: Callable, *args, **kwargs):
        """Add task to queue without waiting"""
        self.queue.put_nowait((func, args, kwargs))
    
    async def wait_completion(self):
        """Wait for all tasks to complete"""
        await self.queue.join()

# Global task queue instance
task_queue = TaskQueue(max_workers=10)
