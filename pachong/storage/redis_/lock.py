"""Redlock distributed lock implementation for LLM Healer coordination."""

from __future__ import annotations

import uuid

from pachong.storage.redis_.client import get_redis


async def acquire_lock(
    resource: str,
    ttl_ms: int = 30_000,
    retry_count: int = 3,
    retry_delay_ms: int = 500,
) -> str | None:
    """Acquire a distributed lock using Redlock algorithm.

    Returns a lock token (UUID string) if acquired, None otherwise.
    The lock auto-expires after ttl_ms to prevent deadlocks.
    """
    redis = get_redis()
    lock_key = f"redlock:{resource}"
    token = str(uuid.uuid4())

    for attempt in range(retry_count):
        acquired = await redis.set(lock_key, token, px=ttl_ms, nx=True)
        if acquired:
            return token
        if attempt < retry_count - 1:
            await __import__("asyncio", fromlist=["asyncio"]).sleep(retry_delay_ms / 1000)

    return None


async def release_lock(resource: str, token: str) -> bool:
    """Release a distributed lock. Only releases if the token matches (prevents accidental unlocks)."""
    redis = get_redis()
    lock_key = f"redlock:{resource}"

    script = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    else
        return 0
    end
    """
    result = await redis.eval(script, 1, lock_key, token)
    return result == 1


async def with_lock(resource: str, ttl_ms: int = 30_000):
    """Async context manager for Redlock.

    Usage:
        async with with_lock("healer:example.com", ttl_ms=30000) as acquired:
            if acquired:
                # do work
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _manager():
        token = await acquire_lock(resource, ttl_ms)
        try:
            yield token is not None
        finally:
            if token:
                await release_lock(resource, token)

    return _manager()
