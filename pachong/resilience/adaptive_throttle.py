"""PID controller for adaptive per-domain rate limiting.

THE CLOSED-LOOP FEEDBACK SYSTEM:

  ban_detector → ban_score (error signal)
       ↓
  PID controller → computes QPS adjustment
       ↓
  Redis token bucket → updated max_tokens for domain
       ↓
  Worker → obeys new rate limit
       ↓
  ban_detector ← observes new block_rate ← Worker results
       ↓
  (loop continues — system self-regulates)

PID formula:
  output = Kp * error + Ki * integral(error) + Kd * derivative(error)

Where:
  error = target_block_rate - actual_block_rate
  output = adjustment to QPS
"""

from __future__ import annotations

import time

import structlog

from pachong.core.settings import ResilienceSettings
from pachong.resilience import metrics
from pachong.resilience.ban_detector import compute_ban_score
from pachong.scheduler.rate_limiter import update_domain_qps
from pachong.storage.redis_.client import get_redis

logger = structlog.get_logger(__name__)

PID_STATE_KEY = "pid:{domain}:state"


class PIDController:
    """Proportional-Integral-Derivative controller for adaptive rate control."""

    def __init__(self, settings: ResilienceSettings) -> None:
        self.Kp = settings.pid_kp
        self.Ki = settings.pid_ki
        self.Kd = settings.pid_kd
        self.target_block_rate = settings.pid_target_block_rate
        self.update_interval_ms = settings.pid_update_interval_ms
        self.min_qps = settings.min_domain_qps
        self.max_qps = settings.max_domain_qps
        self.default_qps = settings.default_domain_qps

    async def evaluate(self, domain: str) -> dict:
        """Run one PID evaluation cycle for a domain. Includes dead zone (|error|<0.05 → skip)."""
        state = await self._load_state(domain)
        ban_score = await compute_ban_score(domain)
        from pachong.resilience.collector import get_domain_stats
        stats = get_domain_stats(domain)
        actual_block_rate = stats["block_rate"]

        # Dead zone: no adjustment if error is tiny
        error = self.target_block_rate - actual_block_rate
        if abs(error) < 0.05:
            state["last_update"] = time.time()
            await self._save_state(domain, state)
            metrics.domain_qps.labels(domain=domain).set(state["current_qps"])
            return state

        state["i_term"] += error * self.update_interval_ms / 1000
        state["i_term"] = max(-2.0, min(2.0, state["i_term"]))
        d_term = (error - state["last_error"]) / (self.update_interval_ms / 1000)
        state["last_error"] = error

        output = self.Kp * error + self.Ki * state["i_term"] + self.Kd * d_term
        current_qps = state["current_qps"]
        new_qps = current_qps + output * current_qps
        new_qps = max(self.min_qps, min(self.max_qps, new_qps))

        # Per-domain emergency brake (only affects this domain)
        if ban_score > 0.7:
            new_qps = self.min_qps
            logger.warning("pid.emergency_brake_per_domain", domain=domain, ban_score=round(ban_score, 3))

        # Update Redis token bucket
        clamped_qps = await update_domain_qps(domain, new_qps)
        state["current_qps"] = clamped_qps
        state["last_update"] = time.time()

        # Persist state
        await self._save_state(domain, state)

        # Update Prometheus
        metrics.pid_controller_state.labels(domain=domain, term="p_term").set(self.Kp * error)
        metrics.pid_controller_state.labels(domain=domain, term="i_term").set(state["i_term"])
        metrics.pid_controller_state.labels(domain=domain, term="output").set(output)
        metrics.domain_qps.labels(domain=domain).set(clamped_qps)

        logger.info(
            "pid.evaluated",
            domain=domain,
            ban_score=round(ban_score, 3),
            actual_block_rate=round(actual_block_rate, 3),
            error=round(error, 4),
            qps=round(clamped_qps, 2),
            adjustment=round(output, 3),
        )

        return {
            "domain": domain,
            "ban_score": ban_score,
            "error": error,
            "current_qps": clamped_qps,
            "p_term": self.Kp * error,
            "i_term": state["i_term"],
            "d_term": d_term,
        }

    async def _load_state(self, domain: str) -> dict:
        redis = get_redis()
        key = PID_STATE_KEY.format(domain=domain)
        data = await redis.hgetall(key)
        if not data:
            return {
                "current_qps": self.default_qps,
                "i_term": 0.0,
                "last_error": 0.0,
                "last_update": time.time(),
            }
        return {
            "current_qps": float(data.get("current_qps", self.default_qps)),
            "i_term": float(data.get("i_term", 0.0)),
            "last_error": float(data.get("last_error", 0.0)),
            "last_update": float(data.get("last_update", time.time())),
        }

    async def _save_state(self, domain: str, state: dict) -> None:
        redis = get_redis()
        key = PID_STATE_KEY.format(domain=domain)
        await redis.hset(key, mapping={
            "current_qps": str(state["current_qps"]),
            "i_term": str(state["i_term"]),
            "last_error": str(state["last_error"]),
            "last_update": str(state["last_update"]),
        })
        await redis.expire(key, 3600)


async def start_pid_control_loop(domain: str, settings: ResilienceSettings) -> None:
    """Background task that periodically evaluates PID for a domain.

    Runs every update_interval_ms. Stops when ban score is healthy
    and QPS has recovered to default or above.
    """
    controller = PIDController(settings)
    import asyncio

    logger.info("pid.loop_started", domain=domain)

    while True:
        try:
            result = await controller.evaluate(domain)

            # Check if we can exit: ban score low AND QPS at or above default
            if result["ban_score"] < 0.1 and result["current_qps"] >= settings.default_domain_qps:
                logger.info("pid.loop_complete", domain=domain, qps=result["current_qps"])
                break

        except Exception:
            logger.exception("pid.loop_error", domain=domain)

        await asyncio.sleep(settings.pid_update_interval_ms / 1000)
