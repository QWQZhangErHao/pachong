"""Redis-backed proxy pool management.

Proxies are stored in Redis with TTL-based eviction for stale entries.
Health checks run periodically to prune dead proxies.
Bandit algorithms (Phase 4 bandit module) select the best proxy for each request.
"""

from __future__ import annotations

import uuid
from typing import Literal

import structlog

from pachong.core.models import ProxyRecord, ProxyProtocol, ProxyStatus
from pachong.storage.redis_.client import get_redis

logger = structlog.get_logger(__name__)

PROXY_POOL_KEY = "proxy:pool"
PROXY_DETAIL_KEY = "proxy:detail:{proxy_id}"
PROXY_HEALTH_KEY = "proxy:health:{proxy_id}"


async def add_proxy(proxy: ProxyRecord) -> str:
    """Add a proxy to the pool. Returns the proxy_id."""
    redis = get_redis()

    if not proxy.proxy_id:
        proxy.proxy_id = uuid.uuid4()

    # Add to active pool sorted set (score = success_rate * 100)
    await redis.zadd(PROXY_POOL_KEY, {str(proxy.proxy_id): proxy.success_rate * 100})

    # Store full details
    await redis.hset(
        PROXY_DETAIL_KEY.format(proxy_id=str(proxy.proxy_id)),
        mapping={
            "host": proxy.host,
            "port": str(proxy.port),
            "protocol": proxy.protocol.value,
            "username": proxy.username or "",
            "password": proxy.password or "",
            "region": proxy.region,
            "country": proxy.country or "",
            "city": proxy.city or "",
            "lat": str(proxy.latitude or 0),
            "lon": str(proxy.longitude or 0),
            "isp": proxy.isp or "",
            "success_rate": str(proxy.success_rate),
            "ban_score": str(proxy.ban_score),
            "status": proxy.status.value,
        },
    )

    logger.info("proxy.added", proxy_id=str(proxy.proxy_id), host=proxy.host, region=proxy.region)
    return str(proxy.proxy_id)


async def get_proxy(proxy_id: str) -> ProxyRecord | None:
    """Retrieve a proxy's full details."""
    redis = get_redis()
    data = await redis.hgetall(PROXY_DETAIL_KEY.format(proxy_id=proxy_id))
    if not data:
        return None

    return ProxyRecord(
        proxy_id=uuid.UUID(proxy_id),
        protocol=ProxyProtocol(data.get("protocol", "http")),
        host=data.get("host", ""),
        port=int(data.get("port", 0)),
        username=data.get("username") or None,
        password=data.get("password") or None,
        region=data.get("region", "unknown"),
        country=data.get("country") or None,
        city=data.get("city") or None,
        latitude=float(data.get("lat", 0)) or None,
        longitude=float(data.get("lon", 0)) or None,
        isp=data.get("isp") or None,
        success_rate=float(data.get("success_rate", 1.0)),
        ban_score=float(data.get("ban_score", 0.0)),
        status=ProxyStatus(data.get("status", "active")),
    )


async def get_active_proxies(
    min_success_rate: float = 0.3,
    max_ban_score: float = 0.5,
    region: str | None = None,
    limit: int = 50,
) -> list[str]:
    """Get active proxy IDs sorted by success rate.

    Args:
        min_success_rate: Minimum success rate filter
        max_ban_score: Maximum ban score filter
        region: Optional region filter
        limit: Max proxies to return
    """
    redis = get_redis()

    # Get proxies with success_rate >= min_success_rate
    min_score = min_success_rate * 100
    all_proxies = await redis.zrevrangebyscore(
        PROXY_POOL_KEY,
        max=100,
        min=min_score,
        start=0,
        num=limit * 2,  # Fetch extra to allow filtering
    )

    qualified: list[str] = []
    for pid in all_proxies:
        if len(qualified) >= limit:
            break

        detail = await redis.hgetall(PROXY_DETAIL_KEY.format(proxy_id=pid))
        if not detail:
            continue

        ban = float(detail.get("ban_score", 0))
        proxy_region = detail.get("region", "")

        if ban >= max_ban_score:
            continue
        if region and proxy_region != region:
            continue

        qualified.append(pid)

    return qualified


async def remove_proxy(proxy_id: str) -> None:
    """Remove a proxy from the pool."""
    redis = get_redis()
    await redis.zrem(PROXY_POOL_KEY, proxy_id)
    await redis.delete(PROXY_DETAIL_KEY.format(proxy_id=proxy_id))
    await redis.delete(PROXY_HEALTH_KEY.format(proxy_id=proxy_id))
    logger.info("proxy.removed", proxy_id=proxy_id)


async def update_proxy_stats(
    proxy_id: str,
    success_rate: float | None = None,
    ban_score: float | None = None,
    latency_ms: float | None = None,
) -> None:
    """Update proxy performance statistics."""
    redis = get_redis()

    updates: dict[str, str] = {}
    if success_rate is not None:
        updates["success_rate"] = str(success_rate)
        await redis.zadd(PROXY_POOL_KEY, {proxy_id: success_rate * 100})
    if ban_score is not None:
        updates["ban_score"] = str(ban_score)

    if updates:
        await redis.hset(PROXY_DETAIL_KEY.format(proxy_id=proxy_id), mapping=updates)


async def mark_banned(proxy_id: str) -> None:
    """Mark a proxy as banned."""
    redis = get_redis()
    await redis.hset(
        PROXY_DETAIL_KEY.format(proxy_id=proxy_id),
        mapping={"status": "banned", "ban_score": "1.0"},
    )
    await redis.zrem(PROXY_POOL_KEY, proxy_id)
    logger.warning("proxy.banned", proxy_id=proxy_id)


async def pool_stats() -> dict:
    """Get proxy pool summary statistics."""
    redis = get_redis()
    total = await redis.zcard(PROXY_POOL_KEY)
    return {
        "total_proxies": total,
    }
