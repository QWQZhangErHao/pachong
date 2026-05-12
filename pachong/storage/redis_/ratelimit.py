"""Sliding-window rate limiter backed by Redis."""

from __future__ import annotations

import time

from pachong.storage.redis_.client import get_redis


async def check_rate_limit(
    domain: str,
    max_tokens: float = 1.0,
    window_seconds: float = 1.0,
) -> bool:
    """Check if a token is available for the domain.

    Uses a sliding-window approach with Redis sorted sets.
    Returns True if the request can proceed, False if rate-limited.
    """
    redis = get_redis()
    key = f"ratelimit:{domain}:tokens"
    now = time.time()
    window_start = now - window_seconds

    async with redis.pipeline(transaction=True) as pipe:
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        _, current_count = await pipe.execute()

    if current_count < max_tokens:
        await redis.zadd(key, {str(now): now})
        await redis.expire(key, int(window_seconds * 2))
        return True
    return False


async def get_token_availability(domain: str) -> tuple[float, float]:
    """Return (available_tokens, max_tokens) for a domain."""
    redis = get_redis()
    key = f"ratelimit:{domain}:config"
    config = await redis.hgetall(key)
    max_tokens = float(config.get("max_tokens", 1.0))

    token_key = f"ratelimit:{domain}:tokens"
    now = time.time()
    window_seconds = float(config.get("window_seconds", 1.0))
    await redis.zremrangebyscore(token_key, 0, now - window_seconds)
    current = await redis.zcard(token_key)

    return max_tokens - current, max_tokens


async def set_token_bucket_config(
    domain: str,
    max_tokens: float,
    window_seconds: float = 1.0,
) -> None:
    """Configure token bucket parameters for a domain."""
    redis = get_redis()
    key = f"ratelimit:{domain}:config"
    await redis.hset(
        key,
        mapping={
            "max_tokens": str(max_tokens),
            "window_seconds": str(window_seconds),
        },
    )
