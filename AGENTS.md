# AGENTS.md

## Cursor Cloud specific instructions

### Overview

This is a single-service Python Telegram bot (Nagu Downloader Bot) using aiogram 3.x. See `README.md` for full documentation. Entry point is `python bot.py`.

### Running the bot

- The bot requires `BOT_TOKEN` env var (Telegram bot token from @BotFather) to start. Without it, config validation fails immediately.
- `BOT_TOKEN` must be syntactically valid (format `<numeric_id>:<alphanumeric_hash>`) or aiogram will reject it at import time (the `Bot()` instance is created at module-level in `core/bot.py`).
- Redis (`REDIS_URL`, `REDIS_TOKEN`) is optional; the bot degrades gracefully without it but caching, emoji customization, and rate limiting will not function.
- The bot starts a health server on `PORT` (default 8080). Verify with `curl http://localhost:8080/health`.
- Polling will fail with `TelegramUnauthorizedError` if the token is invalid; the bot retries with exponential backoff and does not crash.

### PATH setup

- `pip install -r requirements.txt` installs CLI tools (`yt-dlp`, `spotdl`) to `~/.local/bin`. Ensure `PATH` includes `$HOME/.local/bin` (add `export PATH="$HOME/.local/bin:$PATH"` to your shell if needed).

### System dependencies

- FFmpeg and FFprobe must be on PATH (pre-installed on Cloud VM at `/usr/bin/ffmpeg`).

### Testing

- No test framework (pytest, unittest) is configured. The repo provides `test_imports.py` as a smoke test to verify all module imports work. Run: `BOT_TOKEN="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi" python3 test_imports.py`
- Syntax-check all files: `python3 -m py_compile bot.py && for f in core/*.py downloaders/*.py ui/*.py utils/*.py workers/*.py; do python3 -m py_compile "$f"; done`

### Linting

- No linter configuration exists in the repo (no pyproject.toml, .flake8, setup.cfg, or tox.ini).
