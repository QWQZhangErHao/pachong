"""Crawl frontier — per-domain politeness and scheduling windows.

Ensures the system respects per-domain politeness intervals.
All state is stored in Redis so multiple schedulers can coordinate.
"""

from __future__ import annotations

import time

import structlog

from pachong.storage.redis_.client import get_redis

logger = structlog.get_logger(__name__)

FRONTIER_KEY = "frontier:{domain}:last_request"
DELAY_KEY = "frontier:{domain}:min_delay_ms"


async def can_request(domain: str, min_delay_ms: int = 1_000) -> bool:
    """Check if enough time has passed since the last request to this domain.

    Default: 1 second between requests to the same domain (polite crawling).
    """
    redis = get_redis()
    key = FRONTIER_KEY.format(domain=domain)

    last = await redis.get(key)
    if last is None:
        return True

    elapsed_ms = (time.monotonic() - float(last)) * 1000
    return elapsed_ms >= min_delay_ms


async def mark_requested(domain: str) -> float:
    """Record that a request was just made to this domain. Returns current timestamp."""
    redis = get_redis()
    key = FRONTIER_KEY.format(domain=domain)
    now = time.monotonic()
    await redis.set(key, str(now))
    await redis.expire(key, 3600)
    return now


async def time_until_available(domain: str, min_delay_ms: int = 1_000) -> float:
    """Seconds until the domain can be requested again. 0 = available now."""
    redis = get_redis()
    key = FRONTIER_KEY.format(domain=domain)

    last = await redis.get(key)
    if last is None:
        return 0.0

    elapsed_s = time.monotonic() - float(last)
    remaining_s = (min_delay_ms / 1000) - elapsed_s
    return max(0.0, remaining_s)


async def set_domain_delay(domain: str, min_delay_ms: int) -> None:
    """Configure a custom politeness delay for a domain."""
    redis = get_redis()
    await redis.set(DELAY_KEY.format(domain=domain), str(min_delay_ms))


async def get_domain_delay(domain: str, default_ms: int = 1_000) -> int:
    """Get the configured politeness delay for a domain."""
    redis = get_redis()
    val = await redis.get(DELAY_KEY.format(domain=domain))
    return int(val) if val else default_ms


async def get_frontier_stats() -> dict[str, int]:
    """Return approximate count of domains tracked in the frontier."""
    redis = get_redis()
    keys = await redis.keys(FRONTIER_KEY.format(domain="*"))
    return {"tracked_domains": len(keys)}
