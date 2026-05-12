"""Adaptive engine selector — the central decision hub.

Logic:
1. Try static HTTP/2 first for all requests (fastest path)
2. If response contains JS challenge indicators → escalate to Playwright
3. If Playwright is too slow for the volume → try Lightpanda
4. If specific anti-bot is detected (403, captcha) → use Nodriver for
   cookie acquisition, then fall back to HTTP/2 with acquired cookies
5. Decision is cached per domain+path-pattern in Redis (TTL: 5 minutes)

Key insight: We cache ENGINE CHOICES, not just results. If we previously
determined that domain X needs Playwright, we skip HTTP for N minutes.
"""

from __future__ import annotations

import time
from typing import Protocol

import structlog

from pachong.core.models import BrowserIdentity
from pachong.core.settings import NetworkSettings
from pachong.network.response import FetchResponse
from pachong.storage.redis_.client import get_redis

logger = structlog.get_logger(__name__)

DECISION_CACHE_KEY = "engine:decision:{domain}:{path_hash}"
DECISION_CACHE_TTL = 300  # 5 minutes


class EngineCallable(Protocol):
    """Protocol for any fetch function: async (url, identity, timeout) -> FetchResponse."""

    async def __call__(
        self,
        url: str,
        identity: BrowserIdentity | None = None,
        timeout_ms: int = 30_000,
        cookies: dict[str, str] | None = None,
    ) -> FetchResponse: ...


async def get_cached_engine(domain: str, url: str) -> str | None:
    """Check if we have a cached engine recommendation for this domain+path."""
    redis = get_redis()
    path_hash = hash(url.split("?", 1)[0]) % 100000
    key = DECISION_CACHE_KEY.format(domain=domain, path_hash=path_hash)
    return await redis.get(key)


async def cache_engine_decision(domain: str, url: str, engine: str) -> None:
    """Cache which engine succeeded for this domain+path pattern."""
    redis = get_redis()
    path_hash = hash(url.split("?", 1)[0]) % 100000
    key = DECISION_CACHE_KEY.format(domain=domain, path_hash=path_hash)
    await redis.set(key, engine, ex=DECISION_CACHE_TTL)


async def clear_engine_cache(domain: str) -> None:
    """Clear cached engine decisions for a domain (e.g., after ban recovery)."""
    redis = get_redis()
    pattern = DECISION_CACHE_KEY.format(domain=domain, path_hash="*")
    keys = await redis.keys(pattern)
    if keys:
        await redis.delete(*keys)


class AdaptiveEngineSelector:
    """Orchestrates multi-engine request execution with automatic escalation."""

    def __init__(self, settings: NetworkSettings) -> None:
        self.settings = settings

    async def fetch(
        self,
        url: str,
        domain: str,
        http_fetch: EngineCallable,
        playwright_fetch: EngineCallable | None = None,
        lightpanda_fetch: EngineCallable | None = None,
        nodriver_fetch: EngineCallable | None = None,
        identity: BrowserIdentity | None = None,
        cookies: dict[str, str] | None = None,
        timeout_ms: int = 30_000,
    ) -> FetchResponse:
        """Execute a request through the adaptive engine hierarchy.

        Escalation path:
            HTTP/2 → Playwright → Lightpanda → Nodriver
            (fast)                                 (slow, expensive)

        At each level, JS challenges trigger escalation. Cookies acquired
        by Nodriver are returned for reuse by the http_fetch engine.
        """
        # Check cached engine decision
        cached_engine = await get_cached_engine(domain, url)
        engine_order = self._build_engine_order(cached_engine)

        last_response: FetchResponse | None = None

        for engine_name in engine_order:
            fetch_fn = self._get_engine(engine_name, http_fetch, playwright_fetch, lightpanda_fetch, nodriver_fetch)
            if fetch_fn is None:
                continue

            logger.debug("adaptive.trying", engine=engine_name, url=url)
            response = await fetch_fn(url=url, identity=identity, timeout_ms=timeout_ms, cookies=cookies or {})
            response.engine_used = engine_name
            last_response = response

            # Success — cache and return
            if response.is_success and not response.is_blocked:
                await cache_engine_decision(domain, url, engine_name)
                return response

            # JS challenge detected — escalate to next engine
            if response.is_js_challenge and engine_name != "nodriver":
                logger.info(
                    "adaptive.escalating",
                    from_engine=engine_name,
                    challenge=response.js_challenge_type,
                    url=url,
                )
                continue

            # Blocked by anti-bot — escalate to nodriver (last resort)
            if response.is_blocked and engine_name != "nodriver":
                logger.warning(
                    "adaptive.blocked",
                    engine=engine_name,
                    status=response.status_code,
                    url=url,
                )
                continue

            # If it's nodriver and we got cookies, cache and return
            if engine_name == "nodriver" and response.is_success:
                await cache_engine_decision(domain, url, "nodriver")
                # Cache cookies for subsequent HTTP requests
                if response.cookies:
                    await self._cache_cookies(domain, response.cookies)
                return response

            # Return as-is for terminal failures
            if engine_name == "nodriver" or engine_name == engine_order[-1]:
                return response

        # Shouldn't reach here, but return the last response if we do
        return last_response or FetchResponse(
            url=url, status_code=0, engine_used="none", error="No engine available",
        )

    def _build_engine_order(self, cached: str | None) -> list[str]:
        """Determine the order to try engines. Cached results skip ahead."""
        default_order = ["http", "playwright", "lightpanda", "nodriver"]

        if cached and cached in default_order:
            # Start from the cached engine, but keep http as fallback
            idx = default_order.index(cached)
            return [cached] + [e for e in default_order[:idx] if e != cached] + default_order[idx + 1:]

        return default_order

    def _get_engine(
        self,
        name: str,
        http_fetch: EngineCallable,
        playwright_fetch: EngineCallable | None,
        lightpanda_fetch: EngineCallable | None,
        nodriver_fetch: EngineCallable | None,
    ) -> EngineCallable | None:
        engines: dict[str, EngineCallable | None] = {
            "http": http_fetch,
            "playwright": playwright_fetch,
            "lightpanda": lightpanda_fetch,
            "nodriver": nodriver_fetch,
        }
        return engines.get(name)

    async def _cache_cookies(self, domain: str, cookies: dict[str, str]) -> None:
        """Cache acquired cookies in Redis for reuse by lighter engines."""
        redis = get_redis()
        key = f"cookies:{domain}"
        await redis.hset(key, mapping=cookies)
        await redis.expire(key, 3600)  # 1 hour TTL


async def get_cached_cookies(domain: str) -> dict[str, str]:
    """Retrieve cached cookies for a domain."""
    redis = get_redis()
    return await redis.hgetall(f"cookies:{domain}")
