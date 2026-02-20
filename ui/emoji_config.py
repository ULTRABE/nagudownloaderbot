"""
Emoji Configuration — Premium vs Normal toggle.

Usage:
    from ui.emoji_config import YT, INSTA, PINTEREST, MUSIC, SUCCESS, PROCESS
    from ui.emoji_config import get_emoji

    # Direct key access:
    emoji = get_emoji("SUCCESS")

Never hardcode emojis in handlers. Import from here only.

Keys:
    Platform:   YT, INSTA, PINTEREST, MUSIC, VIDEO, PIN, PLAYLIST
    Status:     SUCCESS, ERROR, PROCESS, FAST, DOWNLOAD, COMPLETE
    Commands:   BROADCAST, INFO, ID, USER, PING
"""

USE_PREMIUM = True  # toggle: True = premium emojis, False = standard

# ─── Unicode fallbacks (always available) ─────────────────────────────────────

UNICODE = {
    # Platform
    "YT":        "🎬",
    "INSTA":     "📸",
    "PINTEREST": "📌",
    "MUSIC":     "🎵",
    "VIDEO":     "🎥",
    "PIN":       "📌",
    "PLAYLIST":  "🎶",
    # Status
    "SUCCESS":   "✓",
    "ERROR":     "⚠",
    "PROCESS":   "⏳",
    "FAST":      "⚡",
    "DOWNLOAD":  "📥",
    "COMPLETE":  "🎉",
    # Commands
    "BROADCAST": "📢",
    "INFO":      "ℹ",
    "ID":        "🆔",
    "USER":      "👤",
    "PING":      "🏓",
}

# ─── Premium overrides (set file_id or emoji string; None = use Unicode) ──────

PREMIUM = {
    # Platform
    "YT":        "🔥",
    "INSTA":     "✨",
    "PINTEREST": "📌",
    "MUSIC":     "🎵",
    "VIDEO":     "🎥",
    "PIN":       "📌",
    "PLAYLIST":  "🎶",
    # Status
    "SUCCESS":   "✅",
    "ERROR":     "⚠",
    "PROCESS":   "⚡",
    "FAST":      "⚡",
    "DOWNLOAD":  "📥",
    "COMPLETE":  "🎉",
    # Commands
    "BROADCAST": "📢",
    "INFO":      "ℹ",
    "ID":        "🆔",
    "USER":      "👤",
    "PING":      "🏓",
}


def get_emoji(key: str) -> str:
    """
    Get emoji for key.

    Safe behavior:
    - If USE_PREMIUM is True and PREMIUM[key] is not None → return premium value
    - Otherwise → return UNICODE fallback
    - If key not found → return empty string (never crashes)
    """
    if USE_PREMIUM:
        premium_value = PREMIUM.get(key)
        if premium_value:
            return premium_value
    return UNICODE.get(key, "")


# ─── Legacy direct-access names (backward compat) ─────────────────────────────
# These are set at module load time for code that does:
#   from ui.emoji_config import YT, SUCCESS, ...

YT        = get_emoji("YT")
INSTA     = get_emoji("INSTA")
PINTEREST = get_emoji("PINTEREST")
MUSIC     = get_emoji("MUSIC")
VIDEO     = get_emoji("VIDEO")
PIN       = get_emoji("PIN")
PLAYLIST  = get_emoji("PLAYLIST")
SUCCESS   = get_emoji("SUCCESS")
ERROR     = get_emoji("ERROR")
PROCESS   = get_emoji("PROCESS")
FAST      = get_emoji("FAST")
DOWNLOAD  = get_emoji("DOWNLOAD")
COMPLETE  = get_emoji("COMPLETE")
BROADCAST = get_emoji("BROADCAST")
INFO      = get_emoji("INFO")
ID        = get_emoji("ID")
USER      = get_emoji("USER")
PING      = get_emoji("PING")
