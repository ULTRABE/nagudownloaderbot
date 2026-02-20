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
    - Checks Redis for admin-assigned custom emoji first (async not available here,
      so this is the sync fallback used at module load time)
    - If USE_PREMIUM is True and PREMIUM[key] is not None → return premium value
    - Otherwise → return UNICODE fallback
    - If key not found → return empty string (never crashes)
    """
    if USE_PREMIUM:
        premium_value = PREMIUM.get(key)
        if premium_value:
            return premium_value
    return UNICODE.get(key, "")


async def get_emoji_async(key: str) -> str:
    """
    Async version of get_emoji — checks Redis for admin-assigned custom emoji.

    Priority:
    1. Redis-stored custom emoji (set via /assign command)
    2. PREMIUM dict (if USE_PREMIUM)
    3. UNICODE fallback

    If stored value looks like a numeric ID → render as Telegram custom emoji HTML.
    If stored value is a unicode emoji → return as-is.
    If not found → return UNICODE fallback.

    Never crashes.
    """
    try:
        from utils.redis_client import redis_client
        redis_key = f"emoji:{key}"
        stored = await redis_client.get(redis_key)
        if stored:
            stored = stored.strip()
            # If it's a numeric ID → it's a custom_emoji_id
            if stored.isdigit():
                fallback = UNICODE.get(key, "•")
                return f'<tg-emoji emoji-id="{stored}">{fallback}</tg-emoji>'
            # Otherwise it's a unicode emoji — return as-is
            return stored
    except Exception:
        pass

    # Fall back to static config
    return get_emoji(key)


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
