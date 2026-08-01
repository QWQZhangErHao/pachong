"""Full-link timeout guard — wraps any async task with a hard deadline."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")

TOTAL_TIMEOUT = 30  # seconds per URL


async def with_timeout(
    coro: Awaitable[T],
    timeout: float = TOTAL_TIMEOUT,
    fallback: Callable[[], T] | None = None,
    label: str = "task",
) -> T:
    """Execute coro with hard deadline. Optionally returns fallback() on timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except TimeoutError:
        logger.warning("timeout.hit", label=label, timeout=timeout)
        if fallback:
            return fallback()
        raise
    except asyncio.CancelledError:
        logger.warning("timeout.cancelled", label=label)
        if fallback:
            return fallback()
        raise
