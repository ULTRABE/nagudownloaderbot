"""
Emoji Configuration — Premium vs Normal toggle.

Usage:
    from ui.emoji_config import get_emoji, get_emoji_async

    # Sync (module-load time, no Redis):
    emoji = get_emoji("SUCCESS")

    # Async (runtime, checks Redis first):
    emoji = await get_emoji_async("SUCCESS")

Never hardcode emojis in handlers. Use get_emoji_async() in async contexts.

Keys (all uppercase):
    Platform:   YT, INSTA, PINTEREST, MUSIC, VIDEO, PIN, PLAYLIST, SPOTIFY
    Status:     SUCCESS, ERROR, PROCESS, FAST, DOWNLOAD, COMPLETE, LOADING, CHECK
    Commands:   BROADCAST, INFO, ID, USER, PING
    Decorative: STAR, FIRE, ROCKET, CROWN, DIAMOND, ZAP, WAVE
    Extra:      PROCESSING, DELIVERED
"""

USE_PREMIUM = True  # toggle: True = premium emojis, False = standard

# ─── Default emoji fallbacks (always available, covers ALL keys) ──────────────
# This is the single source of truth for fallback values.

DEFAULT_EMOJIS: dict[str, str] = {
    # Platform
    "YT":          "🎬",
    "INSTA":       "📸",
    "PINTEREST":   "📌",
    "MUSIC":       "🎵",
    "VIDEO":       "🎥",
    "PIN":         "📌",
    "PLAYLIST":    "🎶",
    "SPOTIFY":     "🎧",
    # Status
    "SUCCESS":     "✅",
    "ERROR":       "⚠",
    "PROCESS":     "⏳",
    "PROCESSING":  "⏳",
    "FAST":        "⚡",
    "DOWNLOAD":    "📥",
    "COMPLETE":    "🎉",
    "LOADING":     "⏳",
    "CHECK":       "✅",
    "DELIVERED":   "✓",
    # Commands
    "BROADCAST":   "📢",
    "INFO":        "ℹ",
    "ID":          "🆔",
    "USER":        "👤",
    "PING":        "🏓",
    # Decorative
    "STAR":        "⭐",
    "FIRE":        "🔥",
    "ROCKET":      "🚀",
    "CROWN":       "👑",
    "DIAMOND":     "💎",
    "ZAP":         "⚡",
    "WAVE":        "👋",
}

# ─── Unicode fallbacks (legacy alias — same as DEFAULT_EMOJIS) ─────────────────
UNICODE = DEFAULT_EMOJIS

# ─── Premium overrides (set emoji string; None = use DEFAULT) ─────────────────
PREMIUM: dict[str, str | None] = {
    # Platform
    "YT":          "🎬",
    "INSTA":       "📸",
    "PINTEREST":   "📌",
    "MUSIC":       "🎵",
    "VIDEO":       "🎥",
    "PIN":         "📌",
    "PLAYLIST":    "🎶",
    "SPOTIFY":     "🎧",
    # Status
    "SUCCESS":     "✅",
    "ERROR":       "⚠",
    "PROCESS":     "⚡",
    "PROCESSING":  "⚡",
    "FAST":        "⚡",
    "DOWNLOAD":    "📥",
    "COMPLETE":    "🎉",
    "LOADING":     "⏳",
    "CHECK":       "✅",
    "DELIVERED":   "✓",
    # Commands
    "BROADCAST":   "📢",
    "INFO":        "ℹ",
    "ID":          "🆔",
    "USER":        "👤",
    "PING":        "🏓",
    # Decorative
    "STAR":        "⭐",
    "FIRE":        "🔥",
    "ROCKET":      "🚀",
    "CROWN":       "👑",
    "DIAMOND":     "💎",
    "ZAP":         "⚡",
    "WAVE":        "👋",
}


def get_emoji(key: str) -> str:
    """
    Sync emoji resolver — no Redis, uses static config only.

    Safe behavior:
    - If USE_PREMIUM is True and PREMIUM[key] is not None → return premium value
    - Otherwise → return DEFAULT_EMOJIS fallback
    - If key not found → return empty string (never crashes)

    Use get_emoji_async() in async contexts for Redis-backed custom emoji.
    """
    if USE_PREMIUM:
        premium_value = PREMIUM.get(key)
        if premium_value:
            return premium_value
    return DEFAULT_EMOJIS.get(key, "")


async def get_emoji_async(key: str) -> str:
    """
    Async emoji resolver — checks Redis for admin-assigned custom emoji first.

    Priority:
    1. Redis-stored custom emoji (set via /assign command)
       - Numeric string → rendered as <tg-emoji emoji-id="...">fallback</tg-emoji>
       - Unicode string → returned as-is
    2. PREMIUM dict (if USE_PREMIUM)
    3. DEFAULT_EMOJIS fallback

    Never crashes — silently falls back on any error.
    Always returns a non-empty string.

    IMPORTANT: Messages using this must use parse_mode="HTML" for
    <tg-emoji> tags to render correctly.
    """
    try:
        from utils.redis_client import redis_client
        redis_key = f"emoji:{key}"
        stored = await redis_client.get(redis_key)
        if stored:
            stored = stored.strip()
            if stored:
                # Numeric ID → Telegram custom emoji HTML tag
                if stored.isdigit():
                    fallback = DEFAULT_EMOJIS.get(key, "•")
                    return f'<tg-emoji emoji-id="{stored}">{fallback}</tg-emoji>'
                # Unicode emoji → return as-is
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
