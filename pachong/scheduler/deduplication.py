"""URL deduplication using Redis Bloom filter.

Prevents re-crawling the same URL within a configurable window.
Uses Redis SET with TTL as a lightweight alternative to a full Bloom filter
(production should use RedisBloom module for memory efficiency at scale).
"""

from __future__ import annotations

import hashlib

from pachong.storage.redis_.client import get_redis

DEDUP_PREFIX = "dedup:url:"
DEFAULT_TTL_HOURS = 24


def _hash_url(url: str) -> str:
    """SHA-256 truncated to 16 chars — compact, collision-resistant enough."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


async def is_seen(url: str) -> bool:
    """Check if a URL has been recently crawled. Returns True if it's a duplicate."""
    redis = get_redis()
    key = f"{DEDUP_PREFIX}{_hash_url(url)}"
    return bool(await redis.exists(key))


async def mark_seen(url: str, ttl_hours: int = DEFAULT_TTL_HOURS) -> None:
    """Mark a URL as seen with a configurable TTL."""
    redis = get_redis()
    key = f"{DEDUP_PREFIX}{_hash_url(url)}"
    await redis.set(key, "1", ex=ttl_hours * 3600)


async def check_and_mark(url: str, ttl_hours: int = DEFAULT_TTL_HOURS) -> bool:
    """Atomic check-and-mark. Returns True if the URL is new (not seen before)."""
    redis = get_redis()
    key = f"{DEDUP_PREFIX}{_hash_url(url)}"
    # SET with NX = only set if not exists
    result = await redis.set(key, "1", ex=ttl_hours * 3600, nx=True)
    return result is True  # True = set succeeded = URL is new


async def dedup_count() -> int:
    """Approximate count of tracked URLs."""
    redis = get_redis()
    keys = await redis.keys(f"{DEDUP_PREFIX}*")
    return len(keys)
