"""DNS cache with prewarming, async refresh, and persistent storage."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

CACHE_FILE = Path(__file__).parent.parent.parent / "dns_cache.json"
DEFAULT_TTL = 60  # seconds
REFRESH_WINDOW = 5  # seconds before TTL expiry to trigger background refresh

# Global cache: domain -> {"reachable": bool, "expire_at": float, "latency_ms": float}
_cache: dict[str, dict[str, Any]] = {}
_refresh_tasks: dict[str, asyncio.Task] = {}
_refresh_locks: dict[str, asyncio.Lock] = {}  # singleflight: per-domain lock
_high_freq_domains: list[str] = []


def _now() -> float:
    return time.monotonic()


def load_from_disk() -> None:
    global _cache
    try:
        if CACHE_FILE.exists():
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            now = _now()
            _cache = {
                k: v for k, v in data.items()
                if v.get("expire_at", 0) > now - 86400
            }
            logger.info("dns_cache.loaded", entries=len(_cache))
    except Exception:
        pass


def save_to_disk() -> None:
    try:
        CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


async def prewarm_domains(domains: list[str]) -> None:
    """Async concurrent resolve of high-frequency domains at startup."""
    global _high_freq_domains
    _high_freq_domains = list(set(domains))
    logger.info("dns_cache.prewarm_start", count=len(_high_freq_domains))

    async def resolve_one(domain: str):
        result = await check_domain_reachable(domain)
        logger.debug("dns_cache.prewarmed", domain=domain, reachable=result["reachable"])

    await asyncio.gather(*[resolve_one(d) for d in _high_freq_domains], return_exceptions=True)
    save_to_disk()
    logger.info("dns_cache.prewarm_done")


async def check_domain_reachable(domain: str) -> dict:
    """Check if a domain is reachable and store result with TTL."""
    entry = _cache.get(domain)
    now = _now()

    # Return cached if still valid
    if entry and entry.get("expire_at", 0) > now:
        # Trigger background refresh if within refresh window
        if entry["expire_at"] - now < REFRESH_WINDOW and domain not in _refresh_tasks:
            _refresh_tasks[domain] = asyncio.create_task(_background_refresh(domain))
        return entry

    # Check connectivity
    start = time.perf_counter()
    reachable = await _tcp_probe(domain)
    latency = (time.perf_counter() - start) * 1000

    entry = {
        "reachable": reachable,
        "latency_ms": round(latency, 1),
        "expire_at": now + DEFAULT_TTL,
        "checked_at": now,
    }
    _cache[domain] = entry

    # Persist periodically (not every check)
    if len(_cache) % 20 == 0:
        save_to_disk()

    return entry


async def _tcp_probe(domain: str, timeout: float = 0.8) -> bool:
    """Quick TCP connect to check reachability."""
    for port in (443, 80):
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(domain, port), timeout=timeout
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            continue
    return False


async def _background_refresh(domain: str) -> None:
    """Refresh DNS cache entry without blocking current request."""
    try:
        reachable = await _tcp_probe(domain)
        now = _now()
        _cache[domain] = {
            "reachable": reachable,
            "latency_ms": _cache.get(domain, {}).get("latency_ms", 0),
            "expire_at": now + DEFAULT_TTL,
            "checked_at": now,
        }
        logger.debug("dns_cache.refreshed", domain=domain, reachable=reachable)
    except Exception:
        pass
    finally:
        _refresh_tasks.pop(domain, None)


def is_reachable(domain: str) -> bool | None:
    """Sync check — returns True/False/None (unknown)."""
    entry = _cache.get(domain)
    if entry and entry.get("expire_at", 0) > _now():
        return entry["reachable"]
    return None


def get_cache_stats() -> dict:
    return {
        "entries": len(_cache),
        "high_freq_domains": len(_high_freq_domains),
        "pending_refreshes": len(_refresh_tasks),
    }


# Auto-load on import
load_from_disk()
