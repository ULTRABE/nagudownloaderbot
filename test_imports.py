#!/usr/bin/env python3
"""Test script to verify all imports work correctly"""

print("Testing imports...")

try:
    print("✓ Testing core imports...")
    from core import config, bot, dp
    print("  ✓ core.config")
    print("  ✓ core.bot")
    print("  ✓ core.dp")
except ImportError as e:
    print(f"  ✗ core imports failed: {e}")
    exit(1)

try:
    print("✓ Testing utils imports...")
    from utils import logger, mention, get_random_cookie, resolve_pinterest_url, redis_client
    print("  ✓ utils.logger")
    print("  ✓ utils.mention")
    print("  ✓ utils.get_random_cookie")
    print("  ✓ utils.resolve_pinterest_url")
    print("  ✓ utils.redis_client")
except ImportError as e:
    print(f"  ✗ utils imports failed: {e}")
    exit(1)

try:
    print("✓ Testing workers imports...")
    from workers import download_semaphore, music_semaphore, spotify_semaphore
    print("  ✓ workers.download_semaphore")
    print("  ✓ workers.music_semaphore")
    print("  ✓ workers.spotify_semaphore")
except ImportError as e:
    print(f"  ✗ workers imports failed: {e}")
    exit(1)

try:
    print("✓ Testing ui imports...")
    from ui import (
        create_progress_bar, SpotifyProgress, DownloadProgress,
        mention, format_user_id, quoted_block, styled_text, premium_panel,
        format_download_complete, format_audio_info, format_spotify_complete,
        format_welcome, format_help_video, format_help_music, format_help_info,
        format_error, format_user_info
    )
    print("  ✓ ui.create_progress_bar")
    print("  ✓ ui.SpotifyProgress")
    print("  ✓ ui.DownloadProgress")
    print("  ✓ ui formatting functions")
except ImportError as e:
    print(f"  ✗ ui imports failed: {e}")
    exit(1)

try:
    print("✓ Testing downloaders imports...")
    from downloaders import (
        handle_instagram, handle_pinterest, handle_youtube,
        handle_spotify_playlist, register_download_handlers
    )
    print("  ✓ downloaders.handle_instagram")
    print("  ✓ downloaders.handle_pinterest")
    print("  ✓ downloaders.handle_youtube")
    print("  ✓ downloaders.handle_spotify_playlist")
    print("  ✓ downloaders.register_download_handlers")
except ImportError as e:
    print(f"  ✗ downloaders imports failed: {e}")
    exit(1)

print("\n✅ All imports successful!")
print("The bot should start without import errors.")
