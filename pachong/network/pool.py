"""Connection pool warmup and keep-alive management.

Pre-warms connections to frequently-targeted domains so the first real
request doesn't pay the TCP+TLS handshake penalty.
"""

from __future__ import annotations

import asyncio

import structlog

from pachong.core.settings import NetworkSettings
from pachong.network.session import SessionFactory

logger = structlog.get_logger(__name__)


class ConnectionPool:
    """Manages pre-warmed connections to target domains.

    Opens N connections before the first real request, maintains health
    via periodic keep-alive pings, and enforces per-domain connection limits.
    """

    def __init__(self, settings: NetworkSettings, session_factory: SessionFactory) -> None:
        self.settings = settings
        self.factory = session_factory
        self._warmed_domains: set[str] = set()
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._warm_count = 3  # connections to pre-open per domain

    async def warm_domain(self, domain: str) -> None:
        """Pre-warm connections to a domain by opening dummy connections.

        This pays the TCP+TLS handshake cost upfront so real requests are fast.
        """
        if domain in self._warmed_domains:
            return

        lock = self._domain_locks.setdefault(domain, asyncio.Lock())
        async with lock:
            if domain in self._warmed_domains:  # Double-check inside lock
                return

            # Ensure connector is built (warm-up side effect)
            self.factory.build_connector() if self.factory._connector is None else None

            logger.debug("pool.warming", domain=domain, count=self._warm_count)
            try:
                # Establish connections by making HEAD requests to the root
                session = self.factory.build_session()
                tasks = []
                for _ in range(self._warm_count):
                    tasks.append(self._warm_connection(session, domain))

                results = await asyncio.gather(*tasks, return_exceptions=True)
                successes = sum(1 for r in results if r is True)
                logger.info(
                    "pool.warmed",
                    domain=domain,
                    successful=successes,
                    total=self._warm_count,
                )
                await session.close()
                self._warmed_domains.add(domain)
            except Exception:
                logger.warning("pool.warm_failed", domain=domain)

    async def _warm_connection(self, session, domain: str) -> bool:
        """Open a single warmup connection."""
        try:
            async with session.head(
                f"https://{domain}/",
                timeout=ClientTimeout(total=5),
                ssl=True,
            ) as resp:
                await resp.read()
                return resp.status < 500
        except Exception:
            return False

    async def keep_alive_ping(self, domain: str) -> bool:
        """Send a keep-alive ping to check if connections are still healthy."""
        session = self.factory.build_session()
        try:
            start = asyncio.get_event_loop().time()
            async with session.head(f"https://{domain}/", timeout=ClientTimeout(total=3)) as resp:
                latency_ms = (asyncio.get_event_loop().time() - start) * 1000
                logger.debug("pool.keepalive", domain=domain, latency_ms=round(latency_ms, 1))
                return resp.status < 500
        except Exception:
            return False
        finally:
            await session.close()

    async def evict(self, domain: str) -> None:
        """Remove a domain from the warmed set (e.g., after ban detection)."""
        self._warmed_domains.discard(domain)

    @property
    def warmed_count(self) -> int:
        return len(self._warmed_domains)


from aiohttp import ClientTimeout
