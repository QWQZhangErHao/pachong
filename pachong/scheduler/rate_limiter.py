"""Redis-backed distributed token bucket for per-domain rate control.

This is the key mechanism that prevents DDoS-like behavior:
each Worker must acquire a token from Redis BEFORE making a request.
Kafka distributes tasks evenly (Round-Robin), while this module
enforces precise per-domain QPS limits globally across all workers.
"""

from __future__ import annotations

import time

import structlog

from pachong.core.settings import ResilienceSettings
from pachong.storage.redis_.client import get_redis

logger = structlog.get_logger(__name__)

TOKEN_KEY = "ratelimit:{domain}:tokens"
CONFIG_KEY = "ratelimit:{domain}:config"


async def try_acquire_token(domain: str, qps: float | None = None) -> bool:
    """Attempt to acquire a token for a domain.

    Returns True if the request may proceed, False if it should be deferred.
    """
    redis = get_redis()
    key = TOKEN_KEY.format(domain=domain)

    if qps is None:
        qps = await _get_configured_qps(domain)

    now = time.monotonic()
    window_start = now - 1.0  # 1-second sliding window

    async with redis.pipeline(transaction=True) as pipe:
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        _, count = await pipe.execute()

    if count < qps:
        await redis.zadd(key, {str(now): now})
        await redis.expire(key, 5)
        logger.debug("ratelimit.token_acquired", domain=domain, current=count + 1, max=qps)
        return True

    logger.debug("ratelimit.token_exhausted", domain=domain, current=count, max=qps)
    return False


async def wait_for_token(domain: str, qps: float | None = None, timeout_ms: int = 30_000) -> bool:
    """Block until a token is available or timeout. Returns True if acquired."""
    import asyncio

    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if await try_acquire_token(domain, qps):
            return True
        await asyncio.sleep(0.1 / max(qps or 1.0, 0.1))
    return False


async def update_domain_qps(domain: str, new_qps: float) -> float:
    """Update QPS for a domain and return the clamped value.

    Used by the PID controller (Phase 6) to dynamically adjust crawl speed.
    """
    from pachong.core.settings import Settings

    settings = Settings.load()
    clamped = max(settings.resilience.min_domain_qps, min(new_qps, settings.resilience.max_domain_qps))
    redis = get_redis()
    await redis.hset(CONFIG_KEY.format(domain=domain), mapping={"qps": str(clamped)})
    logger.info("ratelimit.qps_updated", domain=domain, qps=clamped)
    return clamped


async def get_domain_qps(domain: str, default: float = 1.0) -> float:
    """Get current QPS limit for a domain."""
    return await _get_configured_qps(domain, default)


async def _get_configured_qps(domain: str, default: float = 1.0) -> float:
    redis = get_redis()
    val = await redis.hget(CONFIG_KEY.format(domain=domain), "qps")
    return float(val) if val else default


async def init_domain_config(domain: str, qps: float) -> None:
    """Initialize rate-limit config for a new domain."""
    redis = get_redis()
    await redis.hset(
        CONFIG_KEY.format(domain=domain),
        mapping={"qps": str(qps), "created_at": str(time.time())},
    )
