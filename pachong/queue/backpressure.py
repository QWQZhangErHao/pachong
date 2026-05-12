"""Backpressure controller with token bucket and circuit breaker.

Coordinated through Redis for distributed state — all workers share
the same view of per-domain rate limits and failure counts.
"""

from __future__ import annotations

import time

import structlog

from pachong.storage.redis_.client import get_redis

logger = structlog.get_logger(__name__)


async def get_domain_token(
    domain: str,
    max_qps: float = 1.0,
) -> bool:
    """Attempt to acquire a rate-limit token for a domain.

    Uses Redis sorted set as a sliding-window token bucket.
    Returns True if the request can proceed.
    """
    redis = get_redis()
    key = f"ratelimit:{domain}:tokens"
    now = time.monotonic()
    window_start = now - 1.0

    async with redis.pipeline(transaction=True) as pipe:
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        _, current = await pipe.execute()

    if current < max_qps:
        await redis.zadd(key, {str(now): now})
        await redis.expire(key, 5)
        return True
    return False


async def set_domain_qps(domain: str, qps: float) -> None:
    """Update the max QPS for a domain (used by PID controller in Phase 6)."""
    redis = get_redis()
    await redis.hset(f"ratelimit:{domain}:config", "max_qps", str(qps))


async def get_domain_qps(domain: str, default: float = 1.0) -> float:
    """Read the current max QPS for a domain."""
    redis = get_redis()
    val = await redis.hget(f"ratelimit:{domain}:config", "max_qps")
    return float(val) if val else default


# ── Circuit Breaker ──────────────────────────────────────────────────────────


class CircuitState:
    CLOSED = "closed"  # normal
    OPEN = "open"  # blocking
    HALF_OPEN = "half_open"  # probing


async def record_failure(domain: str) -> int:
    """Record a failure and return the consecutive failure count."""
    redis = get_redis()
    key = f"circuit:{domain}:failures"
    count = await redis.incr(key)
    await redis.expire(key, 600)
    return count


async def record_success(domain: str) -> None:
    """Reset failure counter on success."""
    redis = get_redis()
    await redis.delete(f"circuit:{domain}:failures")


async def get_circuit_state(
    domain: str,
    threshold: int = 10,
    cooldown_s: int = 60,
) -> str:
    """Determine the circuit state for a domain.

    CLOSED → OPEN: consecutive failures >= threshold
    OPEN → HALF_OPEN: cooldown period elapsed
    HALF_OPEN → CLOSED: successful probe
    """
    redis = get_redis()
    failures_key = f"circuit:{domain}:failures"
    state_key = f"circuit:{domain}:state"
    opened_at_key = f"circuit:{domain}:opened_at"

    failures = int(await redis.get(failures_key) or 0)
    state = await redis.get(state_key) or CircuitState.CLOSED
    opened_at = float(await redis.get(opened_at_key) or 0)

    if state == CircuitState.CLOSED and failures >= threshold:
        await redis.set(state_key, CircuitState.OPEN)
        await redis.set(opened_at_key, str(time.monotonic()))
        logger.warning("circuit.open", domain=domain, failures=failures)
        return CircuitState.OPEN

    if state == CircuitState.OPEN:
        if time.monotonic() - opened_at >= cooldown_s:
            await redis.set(state_key, CircuitState.HALF_OPEN)
            logger.info("circuit.half_open", domain=domain)
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN

    if state == CircuitState.HALF_OPEN:
        if failures == 0:
            await redis.set(state_key, CircuitState.CLOSED)
            await redis.delete(opened_at_key)
            logger.info("circuit.closed", domain=domain)
            return CircuitState.CLOSED

    return state


async def is_circuit_open(
    domain: str,
    threshold: int = 10,
    cooldown_s: int = 60,
) -> bool:
    """Convenience check — returns True if the circuit is blocking."""
    state = await get_circuit_state(domain, threshold, cooldown_s)
    return state == CircuitState.OPEN
