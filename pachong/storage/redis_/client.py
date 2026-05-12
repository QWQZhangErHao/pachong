"""redis-py async client with degrade fallback (local cachetools when Redis down)."""

from __future__ import annotations

import structlog
from redis.asyncio import ConnectionPool, Redis

from pachong.core.settings import Settings

logger = structlog.get_logger(__name__)

_pool: ConnectionPool | None = None
_client: Redis | None = None
_degraded: bool = False

# In-memory fallback for critical data when Redis is down
try:
    from cachetools import TTLCache
    _fallback_cache: TTLCache = TTLCache(maxsize=10000, ttl=300)
except ImportError:
    _fallback_cache: dict = {}


def init_redis(settings: Settings) -> Redis:
    """Initialize Redis with max 50 connections."""
    global _pool, _client, _degraded
    try:
        _pool = ConnectionPool.from_url(
            settings.database.redis_uri,
            max_connections=50,
            decode_responses=True,
        )
        _client = Redis(connection_pool=_pool)
        _degraded = False
        return _client
    except Exception:
        _degraded = True
        logger.warning("redis.degraded", reason="connection failed, using local fallback")
        return None


def get_redis() -> Redis | None:
    """Get Redis client, returns None if degraded."""
    if _degraded:
        return None
    if _client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _client


def is_degraded() -> bool:
    return _degraded


def get_fallback(key: str) -> str | None:
    """Get value from local fallback cache."""
    return _fallback_cache.get(key)


def set_fallback(key: str, value: str, ttl: int = 300) -> None:
    """Set value in local fallback cache."""
    _fallback_cache[key] = value
    logger.warning("redis.fallback_used", key=key[:40])


async def close_redis() -> None:
    """Close Redis connections."""
    if _client:
        await _client.aclose()
    if _pool:
        await _pool.disconnect()
