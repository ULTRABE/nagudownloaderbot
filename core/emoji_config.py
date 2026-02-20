"""
Emoji Configuration — Premium vs Normal fallback.

Usage:
    from core.emoji_config import E

    text = f"{E.music} Processing..."
    text = f"{E.check} Done"
    text = f"{E.get('PING')} Pong"

If BOT_HAS_PREMIUM=true → uses Telegram custom emoji HTML tags.
Else → standard Unicode emoji.

To find premium emoji IDs:
  Forward a custom emoji sticker to @userinfobot
  or use @stickers bot to get the emoji ID.

Safe behavior:
  - If premium mode is enabled but file_id is None → falls back to Unicode
  - If key not found → returns "" (never crashes)
"""
import os

# ─── Premium emoji IDs ────────────────────────────────────────────────────────
# Replace these with actual custom emoji IDs from your premium pack.
# Set to None to use Unicode fallback for that key.
_PREMIUM_IDS = {
    # Platform
    "music":     "5368324170671202286",
    "video":     "5368324170671202287",
    "download":  "5368324170671202288",
    "check":     "5368324170671202289",
    "error":     "5368324170671202290",
    "loading":   "5368324170671202291",
    "spotify":   "5368324170671202292",
    "youtube":   "5368324170671202293",
    "instagram": "5368324170671202294",
    "pinterest": "5368324170671202295",
    "star":      "5368324170671202296",
    "fire":      "5368324170671202297",
    "rocket":    "5368324170671202298",
    "crown":     "5368324170671202299",
    "diamond":   "5368324170671202300",
    "zap":       "5368324170671202301",
    "wave":      "5368324170671202302",
    # New keys — set to None until premium IDs are configured
    "success":   None,
    "process":   None,
    "fast":      None,
    "pin":       None,
    "playlist":  None,
    "broadcast": None,
    "info":      None,
    "id":        None,
    "user":      None,
    "ping":      None,
    "complete":  None,
    "insta":     None,
    "yt":        None,
}

# ─── Normal emoji fallbacks ───────────────────────────────────────────────────
_NORMAL = {
    # Platform
    "music":     "🎧",
    "video":     "🎥",
    "download":  "⬇️",
    "check":     "✅",
    "error":     "❌",
    "loading":   "⏳",
    "spotify":   "🎵",
    "youtube":   "▶️",
    "instagram": "📸",
    "pinterest": "📌",
    "star":      "⭐",
    "fire":      "🔥",
    "rocket":    "🚀",
    "crown":     "👑",
    "diamond":   "💎",
    "zap":       "⚡",
    "wave":      "👋",
    # New keys
    "success":   "✓",
    "process":   "⏳",
    "fast":      "⚡",
    "pin":       "📌",
    "playlist":  "🎶",
    "broadcast": "📢",
    "info":      "ℹ",
    "id":        "🆔",
    "user":      "👤",
    "ping":      "🏓",
    "complete":  "🎉",
    "insta":     "📸",
    "yt":        "🎬",
}

# ─── Emoji accessor ───────────────────────────────────────────────────────────

class _EmojiConfig:
    """
    Access emojis as attributes: E.music, E.check, etc.
    Also supports uppercase keys: E.get("SUCCESS"), E.get("PING")

    Automatically uses premium custom emojis if BOT_HAS_PREMIUM=true.

    Safe behavior:
    - If premium mode is enabled but file_id is None → falls back to Unicode
    - If key not found → returns "" (never crashes with KeyError)
    """

    def __init__(self):
        self._premium = os.getenv("BOT_HAS_PREMIUM", "false").lower() in ("true", "1", "yes")

    @property
    def has_premium(self) -> bool:
        return self._premium

    def get(self, name: str) -> str:
        """
        Get emoji by name (case-insensitive).

        Safe: if premium is enabled but file_id is None → Unicode fallback.
        Safe: if key not found → returns "".
        """
        key = name.lower()
        if self._premium:
            eid = _PREMIUM_IDS.get(key)
            if eid:  # Only use premium if file_id is set (not None)
                fallback = _NORMAL.get(key, "•")
                return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
        return _NORMAL.get(key, "")

    def __getattr__(self, name: str) -> str:
        if name.startswith("_"):
            raise AttributeError(name)
        return self.get(name)

    # ─── Convenience properties (existing) ───────────────────────────────────

    @property
    def music(self) -> str:
        return self.get("music")

    @property
    def video(self) -> str:
        return self.get("video")

    @property
    def download(self) -> str:
        return self.get("download")

    @property
    def check(self) -> str:
        return self.get("check")

    @property
    def error(self) -> str:
        return self.get("error")

    @property
    def loading(self) -> str:
        return self.get("loading")

    @property
    def spotify(self) -> str:
        return self.get("spotify")

    @property
    def youtube(self) -> str:
        return self.get("youtube")

    @property
    def instagram(self) -> str:
        return self.get("instagram")

    @property
    def pinterest(self) -> str:
        return self.get("pinterest")

    @property
    def star(self) -> str:
        return self.get("star")

    @property
    def fire(self) -> str:
        return self.get("fire")

    @property
    def rocket(self) -> str:
        return self.get("rocket")

    @property
    def crown(self) -> str:
        return self.get("crown")

    @property
    def diamond(self) -> str:
        return self.get("diamond")

    @property
    def zap(self) -> str:
        return self.get("zap")

    @property
    def wave(self) -> str:
        return self.get("wave")

    # ─── New convenience properties ───────────────────────────────────────────

    @property
    def success(self) -> str:
        return self.get("success")

    @property
    def process(self) -> str:
        return self.get("process")

    @property
    def fast(self) -> str:
        return self.get("fast")

    @property
    def pin(self) -> str:
        return self.get("pin")

    @property
    def playlist(self) -> str:
        return self.get("playlist")

    @property
    def broadcast(self) -> str:
        return self.get("broadcast")

    @property
    def info(self) -> str:
        return self.get("info")

    @property
    def id(self) -> str:
        return self.get("id")

    @property
    def user(self) -> str:
        return self.get("user")

    @property
    def ping(self) -> str:
        return self.get("ping")

    @property
    def complete(self) -> str:
        return self.get("complete")

    @property
    def insta(self) -> str:
        return self.get("insta")

    @property
    def yt(self) -> str:
        return self.get("yt")


# Global emoji instance
E = _EmojiConfig()
