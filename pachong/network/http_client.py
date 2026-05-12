"""Per-domain HTTP/2 client with connection pooling and session reuse."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


class PerDomainSessionPool:
    """Maintains one aiohttp ClientSession per domain for connection reuse.

    Key features:
    - Each domain gets its own session with TCPConnector(limit=0, ttl_dns_cache=300)
    - Sessions are reused across requests to the same domain
    - Idle sessions expire after 120 seconds
    - Connection cleanup runs on session close
    """

    def __init__(self, idle_timeout: int = 120):
        self._sessions: dict[str, aiohttp.ClientSession] = {}
        self._last_used: dict[str, float] = {}
        self._idle_timeout = idle_timeout

    async def get_session(self, domain: str) -> aiohttp.ClientSession:
        """Get or create a session for the domain."""
        now = time.monotonic()

        if domain in self._sessions:
            # Check if session is still valid
            if not self._sessions[domain].closed:
                self._last_used[domain] = now
                return self._sessions[domain]

        # Create new session
        connector = aiohttp.TCPConnector(
            limit=0,  # No per-host limit (controlled by semaphore externally)
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
            force_close=False,
        )
        timeout = aiohttp.ClientTimeout(total=10, connect=3)

        session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=DEFAULT_HEADERS,
        )
        self._sessions[domain] = session
        self._last_used[domain] = now

        logger.debug("http.session_created", domain=domain)
        return session

    async def fetch(
        self,
        domain: str,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> tuple[str, int, dict[str, str]]:
        """Fetch URL using the domain's session. Returns (body, status, headers)."""
        session = await self.get_session(domain)

        req_headers = {**DEFAULT_HEADERS}
        if headers:
            req_headers.update(headers)

        req_timeout = aiohttp.ClientTimeout(total=timeout or 5, connect=1.5)
        try:
            async with session.get(
                url,
                headers=req_headers,
                timeout=req_timeout,
                allow_redirects=True,
                max_redirects=5,
                **kwargs,
            ) as resp:
                body = await resp.text()
                resp_headers = dict(resp.headers)
                return body, resp.status, resp_headers
        except asyncio.TimeoutError:
            return "", 0, {"_error": "timeout"}
        except aiohttp.ClientError as e:
            return "", 0, {"_error": str(e)}

    async def close_domain(self, domain: str) -> None:
        """Close and remove a domain's session."""
        if domain in self._sessions:
            session = self._sessions.pop(domain)
            self._last_used.pop(domain, None)
            if not session.closed:
                await session.close()
            logger.debug("http.session_closed", domain=domain)

    async def close_idle(self) -> int:
        """Close idle sessions. Returns count closed."""
        now = time.monotonic()
        idle_domains = [
            d for d, t in self._last_used.items()
            if now - t > self._idle_timeout
        ]
        for domain in idle_domains:
            await self.close_domain(domain)
        if idle_domains:
            logger.debug("http.idle_cleanup", closed=len(idle_domains))
        return len(idle_domains)

    async def close_all(self) -> None:
        """Close all sessions."""
        for domain in list(self._sessions):
            await self.close_domain(domain)
        logger.info("http.all_sessions_closed")

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)


# Global pool instance
_pool: PerDomainSessionPool | None = None


def get_pool() -> PerDomainSessionPool:
    global _pool
    if _pool is None:
        _pool = PerDomainSessionPool()
    return _pool


async def start_idle_cleanup_task(interval: int = 60) -> None:
    """Background task to periodically clean idle sessions."""
    pool = get_pool()
    while True:
        await asyncio.sleep(interval)
        await pool.close_idle()
