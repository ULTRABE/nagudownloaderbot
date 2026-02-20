"""UI components for bot messages"""
from .progress import create_progress_bar, SpotifyProgress, DownloadProgress
from .formatting import (
    # Core primitives
    mention, format_user_id, format_delivered_with_mention,
    mono, bold, code_panel,
    # Legacy compat
    quoted_block, styled_text, premium_panel,
    # Download status
    format_delivered, format_downloading, format_progress, format_processing,
    format_error,
    # Welcome / help
    format_welcome, format_help_video, format_help_music, format_help_info,
    # User info
    format_user_info, format_id, format_chatid, format_myinfo,
    # Admin
    format_admin_panel, format_status,
    # Spotify
    format_playlist_progress, format_playlist_final, format_playlist_dm_complete,
    format_playlist_detected, format_spotify_complete,
    # Broadcast
    format_broadcast_report, format_broadcast_started,
    # Legacy compat
    format_download_complete, format_audio_info,
)

__all__ = [
    'create_progress_bar', 'SpotifyProgress', 'DownloadProgress',
    'mention', 'format_user_id', 'format_delivered_with_mention',
    'mono', 'bold', 'code_panel',
    'quoted_block', 'styled_text', 'premium_panel',
    'format_delivered', 'format_downloading', 'format_progress', 'format_processing',
    'format_error',
    'format_welcome', 'format_help_video', 'format_help_music', 'format_help_info',
    'format_user_info', 'format_id', 'format_chatid', 'format_myinfo',
    'format_admin_panel', 'format_status',
    'format_playlist_progress', 'format_playlist_final', 'format_playlist_dm_complete',
    'format_playlist_detected', 'format_spotify_complete',
    'format_broadcast_report', 'format_broadcast_started',
    'format_download_complete', 'format_audio_info',
]
