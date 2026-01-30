"""Downloaders module for various platforms"""
from .instagram import handle_instagram
from .pinterest import handle_pinterest
from .youtube import handle_youtube
from .mp3 import handle_mp3_search
from .spotify import handle_spotify_playlist
from .router import register_download_handlers

__all__ = [
    'handle_instagram',
    'handle_pinterest',
    'handle_youtube',
    'handle_mp3_search',
    'handle_spotify_playlist',
    'register_download_handlers'
]
