"""Circuit breaker pattern — prevents hammering domains that are actively blocking.

States:
  CLOSED → normal operation, requests allowed
  OPEN → blocking all requests (after threshold failures)
  HALF_OPEN → allowing a few probe requests to test recovery

State is shared across all workers via Redis.
"""

from __future__ import annotations

import time
from enum import Enum

import structlog

from pachong.storage.redis_.client import get_redis

logger = structlog.get_logger(__name__)

STATE_KEY = "circuit_breaker:{domain}:state"
FAILURES_KEY = "circuit_breaker:{domain}:failures"
OPENED_AT_KEY = "circuit_breaker:{domain}:opened_at"
HALF_OPEN_COUNT_KEY = "circuit_breaker:{domain}:half_open_count"


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


async def is_allowed(domain: str, threshold: int = 10, cooldown_s: int = 60, max_half_open: int = 3) -> bool:
    """Check if a request to this domain is allowed.

    Returns True if request can proceed, False if circuit is open.
    """
    redis = get_redis()
    state = await redis.get(STATE_KEY.format(domain=domain))

    if state is None or state == CircuitState.CLOSED.value:
        return True

    if state == CircuitState.OPEN.value:
        opened_at = float(await redis.get(OPENED_AT_KEY.format(domain=domain)) or 0)
        if time.monotonic() - opened_at >= cooldown_s:
            # Transition to HALF_OPEN
            await redis.set(STATE_KEY.format(domain=domain), CircuitState.HALF_OPEN.value)
            await redis.set(HALF_OPEN_COUNT_KEY.format(domain=domain), "0")
            logger.info("circuit.half_open", domain=domain)
            return True  # Allow this probe request
        return False  # Still blocked

    if state == CircuitState.HALF_OPEN.value:
        # Allow up to max_half_open probe requests
        count = int(await redis.incr(HALF_OPEN_COUNT_KEY.format(domain=domain)))
        await redis.expire(HALF_OPEN_COUNT_KEY.format(domain=domain), cooldown_s)
        return count <= max_half_open

    return True


async def record_success(domain: str) -> None:
    """Record a successful request. Resets circuit if half-open."""
    redis = get_redis()
    state = await redis.get(STATE_KEY.format(domain=domain))

    if state == CircuitState.HALF_OPEN.value:
        await redis.set(STATE_KEY.format(domain=domain), CircuitState.CLOSED.value)
        await redis.delete(FAILURES_KEY.format(domain=domain))
        await redis.delete(OPENED_AT_KEY.format(domain=domain))
        await redis.delete(HALF_OPEN_COUNT_KEY.format(domain=domain))
        logger.info("circuit.closed_recovered", domain=domain)
    elif state == CircuitState.CLOSED.value:
        # Reset failure counter on success in closed state
        await redis.delete(FAILURES_KEY.format(domain=domain))


async def record_failure(domain: str, threshold: int = 10) -> None:
    """Record a failed request. Opens circuit if threshold exceeded."""
    redis = get_redis()

    state = await redis.get(STATE_KEY.format(domain=domain)) or CircuitState.CLOSED.value

    if state == CircuitState.CLOSED.value:
        failures = await redis.incr(FAILURES_KEY.format(domain=domain))
        await redis.expire(FAILURES_KEY.format(domain=domain), 3600)

        if failures >= threshold:
            await redis.set(STATE_KEY.format(domain=domain), CircuitState.OPEN.value)
            await redis.set(OPENED_AT_KEY.format(domain=domain), str(time.monotonic()))
            logger.warning("circuit.opened", domain=domain, failures=failures)

    elif state == CircuitState.HALF_OPEN.value:
        # A failure in half-open sends us back to open
        await redis.set(STATE_KEY.format(domain=domain), CircuitState.OPEN.value)
        await redis.set(OPENED_AT_KEY.format(domain=domain), str(time.monotonic()))
        logger.warning("circuit.reopened", domain=domain, reason="half_open_probe_failed")


async def get_circuit_status(domain: str) -> dict:
    """Get the current circuit breaker status for a domain."""
    redis = get_redis()
    return {
        "domain": domain,
        "state": await redis.get(STATE_KEY.format(domain=domain)) or CircuitState.CLOSED.value,
        "failures": int(await redis.get(FAILURES_KEY.format(domain=domain)) or 0),
        "opened_at": float(await redis.get(OPENED_AT_KEY.format(domain=domain)) or 0),
    }


async def reset_circuit(domain: str) -> None:
    """Manually reset the circuit breaker for a domain."""
    redis = get_redis()
    await redis.delete(STATE_KEY.format(domain=domain))
    await redis.delete(FAILURES_KEY.format(domain=domain))
    await redis.delete(OPENED_AT_KEY.format(domain=domain))
    await redis.delete(HALF_OPEN_COUNT_KEY.format(domain=domain))
    logger.info("circuit.manually_reset", domain=domain)


# ── Operational circuit breakers ─────────────────────────────────────────────


class OperationalBreaker:
    """In-memory circuit breaker for operational components (LLM, Playwright).

    Unlike domain-level breakers, these use in-memory state since they
    protect local components, not remote hosts.
    """

    def __init__(self, name: str, threshold: int = 5, cooldown: float = 30.0):
        self.name = name
        self.threshold = threshold
        self.cooldown = cooldown
        self._failures = 0
        self._opened_at = 0.0
        self._state = CircuitState.CLOSED.value

    @property
    def is_open(self) -> bool:
        import time
        if self._state == CircuitState.CLOSED.value:
            return False
        if self._state == CircuitState.OPEN.value:
            if time.monotonic() - self._opened_at >= self.cooldown:
                self._state = CircuitState.HALF_OPEN.value
                self._failures = 0
                logger.info("op_breaker.half_open", name=self.name)
                return False
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        if self._state != CircuitState.CLOSED.value:
            self._state = CircuitState.CLOSED.value
            logger.info("op_breaker.closed", name=self.name)

    def record_failure(self) -> None:
        import time
        self._failures += 1
        if self._failures >= self.threshold and self._state == CircuitState.CLOSED.value:
            self._state = CircuitState.OPEN.value
            self._opened_at = time.monotonic()
            logger.warning("op_breaker.opened", name=self.name, failures=self._failures)


# Singleton operational breakers
_llm_breaker = OperationalBreaker("llm", threshold=5, cooldown=30.0)
_playwright_breaker = OperationalBreaker("playwright", threshold=3, cooldown=60.0)


def get_llm_breaker() -> OperationalBreaker:
    return _llm_breaker


def get_playwright_breaker() -> OperationalBreaker:
    return _playwright_breaker
