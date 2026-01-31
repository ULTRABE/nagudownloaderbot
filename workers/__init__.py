"""Worker module for async task management"""
from .task_queue import download_semaphore, music_semaphore, spotify_semaphore

__all__ = ['download_semaphore', 'music_semaphore', 'spotify_semaphore']
