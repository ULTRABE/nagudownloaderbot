"""
Proxy Manager — Centralized proxy pool with validation, persistence, and admin controls.

Features:
  - Loads proxies from ENV (PROXIES) + Redis (persistent) + built-in defaults
  - Validates all proxies at startup — removes dead ones from the live pool
  - Dead proxies are NOT discarded entirely; they are retried on /clean
  - Admin commands: /addpxy, /rm, /clean
  - pick_proxy() returns random live proxy for any handler
  - Supports formats: IP:PORT, IP:PORT:USER:PASS, http://IP:PORT, socks5://IP:PORT

Startup validation:
  - All proxies are tested concurrently (50 at a time) during initialize()
  - Dead proxies are removed from the live pool immediately
  - This keeps pick_proxy() returning only working proxies
  - /clean re-validates and removes dead ones from the all-pool too

Usage:
    from utils.proxy_manager import proxy_manager

    # On startup (called from bot.py):
    await proxy_manager.initialize()

    # In any downloader:
    proxy = proxy_manager.pick_proxy()
"""
import asyncio
import random
from typing import List, Optional, Set, Tuple

import aiohttp

from utils.logger import logger

# ─── Redis key for persistent proxy storage ───────────────────────────────────
_REDIS_KEY = "proxies:all"
_REDIS_LIVE_KEY = "proxies:live"

# ─── Validation settings ──────────────────────────────────────────────────────
_VALIDATION_URL = "http://httpbin.org/ip"
_VALIDATION_TIMEOUT = 10      # seconds per proxy
_VALIDATION_CONCURRENCY = 50  # max simultaneous checks
_STARTUP_VALIDATION_TIMEOUT = 12  # slightly longer on startup

# ─── Built-in default proxy pool (authenticated) ─────────────────────────────
# Format: IP:PORT:USER:PASS → normalized to http://USER:PASS@IP:PORT
# These are loaded on startup, validated, and only live ones are used.

_DEFAULT_PROXIES = [
    "170.130.62.24:8800:203033:JmNd95Z3vcX",
    "170.130.62.221:8800:203033:JmNd95Z3vcX",
    "77.83.170.91:8800:203033:JmNd95Z3vcX",
    "196.51.221.125:8800:203033:JmNd95Z3vcX",
    "196.51.82.59:8800:203033:JmNd95Z3vcX",
    "196.51.221.174:8800:203033:JmNd95Z3vcX",
    "196.51.106.30:8800:203033:JmNd95Z3vcX",
    "196.51.85.156:8800:203033:JmNd95Z3vcX",
    "196.51.106.100:8800:203033:JmNd95Z3vcX",
    "170.130.62.151:8800:203033:JmNd95Z3vcX",
    "196.51.106.117:8800:203033:JmNd95Z3vcX",
    "196.51.221.38:8800:203033:JmNd95Z3vcX",
    "196.51.85.213:8800:203033:JmNd95Z3vcX",
    "196.51.82.106:8800:203033:JmNd95Z3vcX",
    "196.51.109.138:8800:203033:JmNd95Z3vcX",
    "170.130.62.211:8800:203033:JmNd95Z3vcX",
    "196.51.82.198:8800:203033:JmNd95Z3vcX",
    "77.83.170.79:8800:203033:JmNd95Z3vcX",
    "196.51.85.7:8800:203033:JmNd95Z3vcX",
    "196.51.85.207:8800:203033:JmNd95Z3vcX",
    "196.51.82.238:8800:203033:JmNd95Z3vcX",
    "196.51.106.69:8800:203033:JmNd95Z3vcX",
    "196.51.218.250:8800:203033:JmNd95Z3vcX",
    "196.51.109.151:8800:203033:JmNd95Z3vcX",
    "170.130.62.42:8800:203033:JmNd95Z3vcX",
    "196.51.109.8:8800:203033:JmNd95Z3vcX",
    "170.130.62.251:8800:203033:JmNd95Z3vcX",
    "196.51.221.46:8800:203033:JmNd95Z3vcX",
    "196.51.106.149:8800:203033:JmNd95Z3vcX",
    "196.51.218.227:8800:203033:JmNd95Z3vcX",
    "196.51.218.236:8800:203033:JmNd95Z3vcX",
    "196.51.106.16:8800:203033:JmNd95Z3vcX",
    "77.83.170.168:8800:203033:JmNd95Z3vcX",
    "196.51.109.31:8800:203033:JmNd95Z3vcX",
    "196.51.218.60:8800:203033:JmNd95Z3vcX",
    "170.130.62.27:8800:203033:JmNd95Z3vcX",
    "77.83.170.124:8800:203033:JmNd95Z3vcX",
    "77.83.170.222:8800:203033:JmNd95Z3vcX",
    "196.51.82.112:8800:203033:JmNd95Z3vcX",
    "196.51.221.102:8800:203033:JmNd95Z3vcX",
    "77.83.170.30:8800:203033:JmNd95Z3vcX",
    "196.51.218.179:8800:203033:JmNd95Z3vcX",
    "196.51.85.59:8800:203033:JmNd95Z3vcX",
    "196.51.218.169:8800:203033:JmNd95Z3vcX",
    "196.51.109.52:8800:203033:JmNd95Z3vcX",
    "170.130.62.223:8800:203033:JmNd95Z3vcX",
    "196.51.85.127:8800:203033:JmNd95Z3vcX",
    "196.51.221.158:8800:203033:JmNd95Z3vcX",
    "196.51.109.6:8800:203033:JmNd95Z3vcX",
    "196.51.82.120:8800:203033:JmNd95Z3vcX",
]


# ─── Proxy format normalization ───────────────────────────────────────────────

def _normalize(proxy: str) -> str:
    """
    Normalize proxy to http://[user:pass@]ip:port format.

    Supported inputs:
      ip:port                → http://ip:port
      ip:port:user:pass      → http://user:pass@ip:port
      user:pass@ip:port      → http://user:pass@ip:port
      http://...             → as-is
      socks5://...           → as-is
    """
    proxy = proxy.strip()
    if not proxy:
        return ""

    # Already has scheme — return as-is
    if proxy.startswith(("http://", "https://", "socks4://", "socks5://")):
        return proxy

    # Check for IP:PORT:USER:PASS format (4 colon-separated parts)
    parts = proxy.split(":")
    if len(parts) == 4:
        ip, port, user, passwd = parts
        return f"http://{user}:{passwd}@{ip}:{port}"

    # Check for user:pass@ip:port format
    if "@" in proxy:
        return f"http://{proxy}"

    # Simple ip:port
    if len(parts) == 2:
        return f"http://{proxy}"

    return f"http://{proxy}"


# ─── ProxyManager ─────────────────────────────────────────────────────────────

class ProxyManager:
    """
    Centralized proxy pool with startup validation, persistence, and admin controls.

    On startup:
      1. Load proxies from: built-in defaults + ENV PROXIES + Redis
      2. Validate ALL proxies concurrently — remove dead ones from live pool
      3. Only live proxies are used for downloads
      4. Dead proxies are kept in _all for reference (re-tested on /clean)

    Runtime:
      - pick_proxy() → random live proxy (or None if all dead)
      - add_proxies() → validate + add to pool + Redis
      - remove_proxy() → remove from pool + Redis
      - clean() → re-validate all, remove dead
    """

    def __init__(self):
        self._live: List[str] = []       # Live proxies (ready to use)
        self._all: Set[str] = set()      # All known proxies (normalized)
        self._initialized = False

    async def initialize(self):
        """
        Load all proxy sources and validate them at startup.
        Dead proxies are excluded from the live pool immediately.
        Bot can still work without proxies — pick_proxy() returns None.
        """
        if self._initialized:
            return

        # Collect from all sources
        all_raw: Set[str] = set()

        # Source A: built-in defaults
        for p in _DEFAULT_PROXIES:
            n = _normalize(p)
            if n:
                all_raw.add(n)

        # Source B: ENV variable
        from core.config import config
        for p in config.PROXIES:
            n = _normalize(p)
            if n:
                all_raw.add(n)

        # Source C: Redis (persistent — survives redeployments)
        try:
            from utils.redis_client import redis_client
            members = await redis_client.smembers(_REDIS_KEY)
            for m in members:
                n = _normalize(str(m))
                if n:
                    all_raw.add(n)
        except Exception as e:
            logger.warning(f"Proxy: Redis load failed: {e}")

        self._all = all_raw
        total = len(all_raw)

        if total == 0:
            logger.info("Proxy: No proxies configured — downloads will run without proxy")
            self._live = []
            self._initialized = True
            return

        logger.info(f"Proxy: Validating {total} proxies at startup (this may take ~10-15s)...")

        # Validate all proxies concurrently — only keep live ones
        alive, dead = await self._validate_batch(list(all_raw), timeout=_STARTUP_VALIDATION_TIMEOUT)
        self._live = alive

        # Remove confirmed-dead proxies from _all to keep it clean
        # (they may come back later via /addpxy or /clean)
        for d in dead:
            self._all.discard(d)

        logger.info(
            f"Proxy: {len(alive)}/{total} proxies are live "
            f"({len(dead)} dead removed)"
        )

        if len(alive) == 0:
            logger.warning("Proxy: All proxies are dead! Downloads will run without proxy.")
            logger.warning("Proxy: Use /addpxy to add new proxies or /clean to re-test.")

        # Persist live proxies to Redis
        await self._sync_to_redis()

        self._initialized = True

    async def _validate_one(self, proxy: str, timeout: int = _VALIDATION_TIMEOUT) -> bool:
        """Test a single proxy by making an HTTP request through it."""
        try:
            to = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=to) as session:
                async with session.get(
                    _VALIDATION_URL,
                    proxy=proxy,
                    ssl=False,
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def _validate_batch(
        self, proxies: List[str], timeout: int = _VALIDATION_TIMEOUT
    ) -> Tuple[List[str], List[str]]:
        """Validate a batch of proxies concurrently. Returns (alive, dead)."""
        sem = asyncio.Semaphore(_VALIDATION_CONCURRENCY)
        alive: List[str] = []
        dead: List[str] = []

        async def _check(proxy: str):
            async with sem:
                ok = await self._validate_one(proxy, timeout=timeout)
                if ok:
                    alive.append(proxy)
                else:
                    dead.append(proxy)

        tasks = [asyncio.create_task(_check(p)) for p in proxies]
        await asyncio.gather(*tasks, return_exceptions=True)
        return alive, dead

    async def _sync_to_redis(self):
        """Persist current live proxies to Redis."""
        try:
            from utils.redis_client import redis_client
            await redis_client.delete(_REDIS_KEY)
            if self._live:
                await redis_client.sadd(_REDIS_KEY, *self._live)
        except Exception as e:
            logger.warning(f"Proxy: Redis sync failed: {e}")

    # ─── Public API ───────────────────────────────────────────────────────────

    def pick_proxy(self) -> Optional[str]:
        """Get a random live proxy, or None if pool is empty."""
        return random.choice(self._live) if self._live else None

    def get_stats(self) -> dict:
        """Get proxy pool statistics."""
        return {"total": len(self._all) + len(self._live), "live": len(self._live)}

    def get_live_count(self) -> int:
        return len(self._live)

    async def add_proxies(self, raw_proxies: List[str]) -> Tuple[int, int]:
        """
        Add and validate new proxies.
        Returns (added_count, failed_count).
        Auto-validates each proxy before adding.
        """
        to_check: List[str] = []
        existing = set(self._live) | self._all
        for p in raw_proxies:
            n = _normalize(p)
            if n and n not in existing:
                to_check.append(n)

        if not to_check:
            return 0, 0

        alive, dead = await self._validate_batch(to_check)

        for p in alive:
            self._all.add(p)
            if p not in self._live:
                self._live.append(p)

        await self._sync_to_redis()
        return len(alive), len(dead)

    async def remove_proxy(self, raw_proxy: str) -> bool:
        """Remove a proxy from pool and Redis."""
        n = _normalize(raw_proxy)
        if not n:
            return False

        removed = False
        if n in self._all:
            self._all.discard(n)
            removed = True
        if n in self._live:
            self._live.remove(n)
            removed = True

        if removed:
            await self._sync_to_redis()
        return removed

    async def clean(self) -> Tuple[int, int]:
        """
        Re-validate ALL proxies (live + previously dead defaults).
        Remove dead ones. Returns (alive, removed).
        """
        # Re-add all defaults to give them another chance
        all_to_test: Set[str] = set(self._live) | self._all
        for p in _DEFAULT_PROXIES:
            n = _normalize(p)
            if n:
                all_to_test.add(n)

        if not all_to_test:
            return 0, 0

        logger.info(f"Proxy /clean: testing {len(all_to_test)} proxies...")
        alive, dead = await self._validate_batch(list(all_to_test))

        self._live = alive
        self._all = set(alive)  # Only keep confirmed live proxies in _all

        await self._sync_to_redis()
        logger.info(f"Proxy /clean: {len(alive)} alive, {len(dead)} removed")
        return len(alive), len(dead)


# ─── Global instance ──────────────────────────────────────────────────────────
proxy_manager = ProxyManager()
