"""Proxy health checking — periodically verifies proxies are alive and unblocked.

Uses a simple HTTP request to a known-good endpoint to verify proxy
connectivity and measure latency. Dead/banned proxies are pruned.
"""

from __future__ import annotations

import asyncio
import time

import structlog
from aiohttp import ClientSession, ClientTimeout

from pachong.anti_detect.proxy.pool import (
    get_active_proxies,
    get_proxy,
    mark_banned,
    update_proxy_stats,
)
from pachong.core.models import ProxyRecord

logger = structlog.get_logger(__name__)

# Test endpoints for health checking
TEST_ENDPOINTS = [
    "https://httpbin.org/ip",
    "https://api.ipify.org?format=json",
    "https://ifconfig.me/ip",
]


async def check_proxy_health(proxy_id: str) -> dict:
    """Check a single proxy's health. Returns status dict."""
    proxy = await get_proxy(proxy_id)
    if not proxy:
        return {"proxy_id": proxy_id, "status": "not_found"}

    proxy_url = _build_proxy_url(proxy)

    for endpoint in TEST_ENDPOINTS:
        try:
            start = time.monotonic()
            timeout = ClientTimeout(total=10, connect=5)

            async with ClientSession(timeout=timeout) as session:
                async with session.get(endpoint, proxy=proxy_url) as resp:
                    body = await resp.text()
                    latency_ms = (time.monotonic() - start) * 1000

                    if resp.status == 200 and len(body) > 0:
                        await update_proxy_stats(
                            proxy_id,
                            success_rate=min(1.0, proxy.success_rate + 0.05),
                            latency_ms=latency_ms,
                        )
                        return {
                            "proxy_id": proxy_id,
                            "status": "healthy",
                            "latency_ms": round(latency_ms, 1),
                            "endpoint": endpoint,
                        }

        except Exception:
            continue

    # All endpoints failed
    await update_proxy_stats(proxy_id, success_rate=max(0.05, proxy.success_rate - 0.1))
    logger.warning("proxy.health_check_failed", proxy_id=proxy_id)

    # Ban if success rate drops too low
    if proxy.success_rate < 0.1:
        await mark_banned(proxy_id)

    return {"proxy_id": proxy_id, "status": "unhealthy"}


async def check_all_proxies(limit: int = 100) -> dict:
    """Run health checks on all active proxies.

    Returns summary statistics.
    """
    proxy_ids = await get_active_proxies(limit=limit)
    logger.info("proxy.health_check_started", count=len(proxy_ids))

    # Run checks concurrently (max 10 at a time)
    semaphore = asyncio.Semaphore(10)

    async def check_with_semaphore(pid: str) -> dict:
        async with semaphore:
            return await check_proxy_health(pid)

    results = await asyncio.gather(*[check_with_semaphore(pid) for pid in proxy_ids], return_exceptions=True)

    healthy = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "healthy")
    unhealthy = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "unhealthy")

    logger.info("proxy.health_check_complete", total=len(proxy_ids), healthy=healthy, unhealthy=unhealthy)

    return {
        "total": len(proxy_ids),
        "healthy": healthy,
        "unhealthy": unhealthy,
    }


async def start_health_check_loop(interval_ms: int = 60_000) -> None:
    """Background task that periodically checks proxy health."""
    logger.info("proxy.health_loop_started", interval_ms=interval_ms)

    while True:
        try:
            await check_all_proxies()
        except Exception:
            logger.exception("proxy.health_loop_error")
        await asyncio.sleep(interval_ms / 1000)


def _build_proxy_url(proxy: ProxyRecord) -> str:
    """Build a proxy URL string from a ProxyRecord."""
    auth = ""
    if proxy.username and proxy.password:
        auth = f"{proxy.username}:{proxy.password}@"
    elif proxy.username:
        auth = f"{proxy.username}@"
    return f"{proxy.protocol.value}://{auth}{proxy.host}:{proxy.port}"
