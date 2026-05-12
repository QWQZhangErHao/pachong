"""Middleware pipeline for request processing.

Executed in order for every request:
1. RetryMiddleware: exponential backoff with jitter
2. RedirectMiddleware: follow redirects, track redirect chain
3. CookieMiddleware: inject acquired cookies
4. HeaderMiddleware: inject identity-consistent headers
5. TimingMiddleware: record DNS, TCP, TLS, TTFB, total time
"""

from __future__ import annotations

import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from pachong.core.errors import NetworkError, RateLimitError
from pachong.core.models import BrowserIdentity
from pachong.network.response import FetchResponse

logger = structlog.get_logger(__name__)

FetchFunc = Callable[..., Awaitable[FetchResponse]]
MiddlewareFunc = Callable[[FetchFunc], FetchFunc]


class MiddlewarePipeline:
    """Composable middleware pipeline for request execution."""

    def __init__(self) -> None:
        self._middlewares: list[MiddlewareFunc] = []

    def add(self, middleware: MiddlewareFunc) -> "MiddlewarePipeline":
        self._middlewares.append(middleware)
        return self

    def build(self, handler: FetchFunc) -> FetchFunc:
        """Wrap handler with all registered middleware, innermost first."""
        wrapped = handler
        for mw in reversed(self._middlewares):
            wrapped = mw(wrapped)
        return wrapped

    @classmethod
    def default(cls, identity: BrowserIdentity | None = None, max_retries: int = 3) -> "MiddlewarePipeline":
        """Create a pipeline with all standard middleware."""
        pipeline = cls()
        pipeline.add(retry_middleware(max_retries))
        pipeline.add(timing_middleware())
        if identity:
            pipeline.add(header_middleware(identity))
        return pipeline


# ── Middleware implementations ────────────────────────────────────────────────


def retry_middleware(max_retries: int = 3) -> MiddlewareFunc:
    """Retry on network errors with exponential backoff + jitter."""

    def _middleware(next_handler: FetchFunc) -> FetchFunc:
        async def _wrapper(**kwargs: Any) -> FetchResponse:
            last_error: FetchResponse | None = None

            for attempt in range(max_retries + 1):
                try:
                    response = await next_handler(**kwargs)
                    response.retry_count = attempt

                    # Don't retry on anti-bot blocks — escalate instead
                    if response.is_blocked and not response.is_js_challenge:
                        return response

                    if response.is_success:
                        return response

                    last_error = response

                except (NetworkError, RateLimitError, OSError) as e:
                    last_error = FetchResponse(
                        url=kwargs.get("url", ""),
                        status_code=0,
                        error=str(e),
                        retry_count=attempt,
                    )

                if attempt < max_retries:
                    # Exponential backoff: 1s, 2s, 4s... with 20% jitter
                    delay = (2**attempt) * (0.8 + random.random() * 0.4)
                    logger.debug("middleware.retry", attempt=attempt + 1, delay=round(delay, 2))
                    await __import__("asyncio").sleep(delay)

            return last_error or FetchResponse(
                url=kwargs.get("url", ""),
                status_code=0,
                error="Max retries exceeded",
                retry_count=max_retries,
            )

        return _wrapper

    return _middleware


def timing_middleware() -> MiddlewareFunc:
    """Record precise timing breakdown for every request."""

    def _middleware(next_handler: FetchFunc) -> FetchFunc:
        async def _wrapper(**kwargs: Any) -> FetchResponse:
            start = time.monotonic()
            response = await next_handler(**kwargs)
            if response.timing.total_ms == 0:
                response.timing.total_ms = (time.monotonic() - start) * 1000
            return response

        return _wrapper

    return _middleware


def header_middleware(identity: BrowserIdentity) -> MiddlewareFunc:
    """Inject identity-consistent headers into the request kwargs."""

    def _middleware(next_handler: FetchFunc) -> FetchFunc:
        async def _wrapper(**kwargs: Any) -> FetchResponse:
            kwargs = dict(kwargs)
            headers = dict(kwargs.get("headers", {}))
            if identity.user_agent:
                headers["User-Agent"] = identity.user_agent
            if identity.locale:
                headers["Accept-Language"] = f"{identity.locale},{identity.locale[:2]};q=0.9"
            kwargs["headers"] = headers
            return await next_handler(**kwargs)

        return _wrapper

    return _middleware


def cookie_middleware(cookies: dict[str, str]) -> MiddlewareFunc:
    """Inject cached cookies from previous Nodriver sessions."""

    def _middleware(next_handler: FetchFunc) -> FetchFunc:
        async def _wrapper(**kwargs: Any) -> FetchResponse:
            kwargs = dict(kwargs)
            kwargs["cookies"] = {**cookies, **kwargs.get("cookies", {})}
            return await next_handler(**kwargs)

        return _wrapper

    return _middleware
