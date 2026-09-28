# Scaling Notes — Getting to ~4-5k Users

This bot runs as a **single Railway container**, long-polling Telegram (see the `TelegramConflictError`
backoff loop in `bot.py`). It is not designed to run as multiple instances of the same bot token — don't
scale it by adding replicas. Scale it by (1) giving the one container more CPU/RAM, and (2) tuning the
concurrency env vars below to match what that container can actually do.

## 1. Raise the Railway plan

Every simultaneous download that needs re-encoding runs `ffmpeg`, which is CPU-bound. The two things that
matter most:

- **CPU cores** — this bounds how many ffmpeg encodes can run at once without thrashing.
- **RAM** — yt-dlp + ffmpeg + Telegram uploads for several concurrent jobs; 2GB+ is a reasonable floor for
  real traffic, more if you raise `MAX_CONCURRENT_DOWNLOADS` significantly.
- **Disk** — temp files live under the OS temp dir per job and are cleaned up after send (see
  `periodic_temp_cleanup` in `bot.py` as a fallback sweep). More concurrent jobs = more temp disk used at
  once, even though each job's own files are short-lived.

There's no single "right" tier — start by watching `/status` (admin) under real load (see §3) and raise the
plan if `downloads_used` is pinned at `downloads_total` for sustained periods with users complaining about
slow delivery.

## 2. Concurrency env vars (tune without a redeploy)

These now read from environment variables (previously hardcoded in `core/config.py`), so you can adjust
them from Railway's dashboard and restart, no code change needed:

| Env var                     | Default | What it controls                                      |
|------------------------------|---------|--------------------------------------------------------|
| `MAX_CONCURRENT_DOWNLOADS`   | 12      | Global cap on simultaneous video/photo downloads        |
| `MAX_CONCURRENT_MUSIC`       | 7       | Global cap on simultaneous YT Music downloads           |
| `MAX_CONCURRENT_SPOTIFY`     | 6       | Global cap on simultaneous Spotify playlist downloads   |
| `MAX_CONCURRENT_PER_USER`    | 6       | Per-user cap across all download types                  |
| `FFMPEG_THREADS`             | min(2, cpu_count) | Threads requested per ffmpeg process           |

**Why `FFMPEG_THREADS` matters:** the old default was a flat `8` threads per ffmpeg process. With up to 25
concurrent download/encode slots (12+7+6), that's up to 200 requested threads at once — wildly
oversubscribing any container smaller than a very large box, causing everything to slow down together
under real concurrent load. The new default scales with the container's actual core count. If you raise
your Railway plan's CPU count, you can raise `FFMPEG_THREADS` a bit too, but prefer raising
`MAX_CONCURRENT_*` first — more jobs running efficiently beats fewer jobs each grabbing more threads.

Rule of thumb: keep `FFMPEG_THREADS × (peak simultaneous ffmpeg jobs)` at or below the container's core
count.

## 3. Reading `/status`

`/status` (admin) now reports **real** numbers instead of hardcoded zeros:

- `Active` — total jobs currently holding a global concurrency slot.
- The breakdown line shows `downloads/total`, `music/total`, `spotify/total` usage.

If a bucket is consistently maxed out during peak hours, that's your signal to raise its env var (after
confirming you have the CPU headroom — see §1) rather than guessing.

## 4. Redis (Upstash) usage

Broadcast lists, warns, cooldowns, the file-id cache, and the proxy pool all live in Upstash Redis, which
bills by request count on most plans. At 4-5k users, watch your Upstash dashboard for request volume in
the first couple of weeks after scaling up, and move to a higher Upstash tier if you approach its limits —
no code changes are expected to be needed for this unless a specific hot path shows up as disproportionate.

## 5. The downloader no longer uses proxies or cookies

`downloaders/instagram.py` and `downloaders/youtube.py` (which also powers Shorts and YT Music) now
download **direct-only** — no proxy, no cookie file, ever, in the hot path. Instead of one attempt with a
slow sequential cookie fallback behind it, each platform races 3 direct layers (different User-Agents for
Instagram; different yt-dlp `player_client` values for YouTube) in parallel and returns as soon as the
first one succeeds, cancelling the rest. This is both faster (no more waiting out a proxy/cookie fallback
chain) and removes two unreliable, credential-bearing dependencies from the request path entirely.

Why: proxies cost money and die constantly (the audit found the pool depends on an external, sometimes
rate-limited validation endpoint); cookie files are live session credentials, and the audit found real,
committed sessions in this repo. Racing plain direct requests sidesteps both.

**Trade-off, on purpose:** private accounts, age-restricted, and sign-in-walled content genuinely need an
authenticated cookie — there's no way around that technically — and will now fail with a clean "unable to
process this link" instead of succeeding via a cookie retry. Public posts, reels, and videos (the large
majority of real requests) are unaffected.

What's left as-is, not removed:
- `cookies_instagram.txt`, `ig cookies/`, `yt cookies/`, `yt music cookies/` still exist on disk (per your
  earlier decision) but are no longer read by the downloader. The cookies in them are still live/real —
  rotate them when convenient regardless, since anyone with read access to this repo (including its git
  history) can use them to act as those accounts.
- `utils/proxy_manager.py` and the `/addpxy` / `/rm` / `/clean` admin commands are untouched and still
  work, even though nothing in `downloaders/` calls `proxy_manager` anymore (Pinterest and Spotify's
  proxy calls were removed too, since they were already optional and unused in practice). The pool stays
  available in case a platform-specific fallback is ever wanted again — it's just fully disconnected from
  downloads for now. Proxy credentials that were previously only hardcoded in `utils/proxy_manager.py` can
  also be supplied via the `DEFAULT_PROXIES` env var instead.
