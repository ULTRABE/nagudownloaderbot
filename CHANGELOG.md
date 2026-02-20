# Changelog — Nagu Downloader Bot

All notable changes are documented here.

---

## [3.0.0] — 2026-02-20

### Added
- **Async Emoji Resolver** (`ui/emoji_config.py`)
  - `get_emoji_async(key)` checks Redis first, falls back to `DEFAULT_EMOJIS`
  - Numeric IDs rendered as `<tg-emoji emoji-id="...">` HTML for Telegram premium emoji
  - `DEFAULT_EMOJIS` dict covers all 27 UI keys
  - Never crashes — always returns a non-empty string

- **Download Log Channel** (`utils/log_channel.py`)
  - Every download logged to a private Telegram channel
  - Clickable user mention via `tg://user?id=`
  - Public groups show clickable link; private groups show title; private chat shows "Private"
  - Accepts `chat=` object (preferred) or `chat_type=` string (legacy compat)

- **Admin Emoji Assignment** (`downloaders/router.py`)
  - `/assign` command accepts Telegram premium custom emoji entities
  - Also accepts plain unicode emoji characters
  - Stored in Redis under `emoji:{KEY}`

- **`ui_title()` helper** (`ui/formatting.py`)
  - Centralized heading wrapper for consistent bold styling

### Changed
- **All formatting functions are now async** (`ui/formatting.py`)
  - `format_delivered_with_mention`, `format_welcome`, `format_help`, `format_myinfo`,
    `format_id`, `format_chatid`, `format_status`, `format_processing`, `format_progress`,
    `format_delivered`, `format_error`, `format_playlist_detected`, `format_playlist_final`,
    `format_yt_playlist_final`, `format_broadcast_started`, `format_broadcast_report`,
    `format_stats`, `format_admin_panel`
  - All use `get_emoji_async()` — emojis are dynamic at runtime

- **All downloaders updated** to `await` async formatting functions and use `get_emoji_async()`
  - `downloaders/instagram.py`, `downloaders/pinterest.py`, `downloaders/spotify.py`,
    `downloaders/youtube.py`, `downloaders/router.py`

- **`utils/broadcast.py`** — `await format_broadcast_report()`, uses `get_emoji_async("BROADCAST")`

- **`utils/error_handler.py`** — All methods now async, use `get_emoji_async()` for all symbols

- **`core/config.py`** — `ADMIN_IDS` changed from list to set for O(1) lookup

- **`format_welcome()`** — Removed promotional/marketing text; clean minimal message

- **`format_assign_prompt()`** — Updated to accept premium emoji or unicode (not stickers)

### Fixed
- Log channel now shows clickable user mentions instead of plain text names
- Log channel now shows clickable group links for public groups

---

## [2.1.0] — 2026-02-15

### Added
- **YouTube Playlist Support** — Audio and video playlist downloads with quality selection
- **YouTube Music Handler** — 320kbps MP3 from YouTube Music URLs
- **Spotify Playlist Streaming** — Track-by-track download via Spotify API (no full playlist spotdl)
- **URL Cache** — Redis-backed `file_id` cache for instant re-sends
- **Per-User Slot Watchdog** — Prevents concurrent download abuse
- **Sticker System** — Platform-specific animated stickers during download
- **`/mp3` Command** — Extract audio from any replied video as 192kbps MP3
- **`/broadcast`** — Admin mass messaging to all users and groups
- **`/ping`** — Health check with latency display
- **`/stats`** — User and group count statistics

### Changed
- Spotify now works in both private and group chats (single tracks always in same chat)
- YouTube normal videos show inline `[Video] [Audio]` buttons before downloading
- Progress bars simplified to clean `[████░░░░░░] 60%` format

---

## [2.0.0] — 2026-01-29

### Added
- Complete rewrite as a downloader-only bot
- Spotify single track + playlist support
- User state management (registration, cooldown, block detection)
- Redis-backed broadcast system
- Premium UI with Unicode styled headings
- Cookie rotation for YouTube and Instagram
- Proxy support

### Removed
- All admin/moderation features (promote, demote, mute, ban, filters)
- Whisper command
- Permission detection systems

---

## [1.0.0] — 2026-01-15

### Initial Release
- Basic Instagram, YouTube, Pinterest download support
- Simple error handling
- Docker support
- Railway deployment support
