"""
Emoji Configuration — Premium vs Normal fallback.

Usage:
    from core.emoji_config import E

    text = f"{E.music} Processing..."
    text = f"{E.check} Done"

If BOT_HAS_PREMIUM=true → uses Telegram custom emoji HTML tags.
Else → standard Unicode emoji.

To find premium emoji IDs:
  Forward a custom emoji sticker to @userinfobot
  or use @stickers bot to get the emoji ID.
"""
import os

# ─── Premium emoji IDs ────────────────────────────────────────────────────────
# Replace these with actual custom emoji IDs from your premium pack.
_PREMIUM_IDS = {
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
}

# ─── Normal emoji fallbacks ───────────────────────────────────────────────────
_NORMAL = {
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
}

# ─── Emoji accessor ───────────────────────────────────────────────────────────

class _EmojiConfig:
    """
    Access emojis as attributes: E.music, E.check, etc.
    Automatically uses premium custom emojis if BOT_HAS_PREMIUM=true.
    """

    def __init__(self):
        self._premium = os.getenv("BOT_HAS_PREMIUM", "false").lower() in ("true", "1", "yes")

    @property
    def has_premium(self) -> bool:
        return self._premium

    def get(self, name: str) -> str:
        """Get emoji by name"""
        if self._premium and name in _PREMIUM_IDS:
            fallback = _NORMAL.get(name, "•")
            eid = _PREMIUM_IDS[name]
            return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
        return _NORMAL.get(name, "•")

    def __getattr__(self, name: str) -> str:
        if name.startswith("_"):
            raise AttributeError(name)
        return self.get(name)

    # ─── Convenience properties ───────────────────────────────────────────────

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


# Global emoji instance
E = _EmojiConfig()
