"""
Emoji Configuration — Premium vs Normal toggle.

Usage:
    from ui.emoji_config import YT, INSTA, PINTEREST, MUSIC, SUCCESS, PROCESS

Never hardcode emojis in handlers. Import from here only.
"""

USE_PREMIUM = True  # toggle: True = premium emojis, False = standard

if USE_PREMIUM:
    YT        = "🔥"
    INSTA     = "✨"
    PINTEREST = "📌"
    MUSIC     = "🎵"
    SUCCESS   = "✅"
    PROCESS   = "⚡"
else:
    YT        = "🎬"
    INSTA     = "📸"
    PINTEREST = "📌"
    MUSIC     = "🎵"
    SUCCESS   = "✓"
    PROCESS   = "⏳"
