"""Target site danger index monitor.

Continuously analyzes 403/Captcha/blank-page ratios to compute
a per-domain "danger index" [0.0-1.0].

This is the primary INPUT signal for the PID controller.
When danger index rises, PID reduces the Redis token bucket rate.
"""

from __future__ import annotations

import structlog

from pachong.resilience import metrics
from pachong.resilience.collector import get_domain_stats
from pachong.storage.redis_.client import get_redis

logger = structlog.get_logger(__name__)

BAN_SCORE_KEY = "ban_score:{domain}"
BAN_WINDOW_KEY = "ban_window:{domain}"


async def compute_ban_score(domain: str) -> float:
    """Compute the current danger index for a domain.

    Formula:
      ban_score = w1 * block_rate + w2 * captcha_rate + w3 * blank_rate

    Where:
      block_rate = 403 / total
      captcha_rate = js_challenge / total
      blank_rate = suspicious empty pages / total

    Smoothing: exponential moving average over previous score.
    """
    stats = get_domain_stats(domain)

    block_rate = stats["block_rate"]
    captcha_rate = stats["captcha_rate"]

    # Weighted composite
    raw_score = (
        0.4 * block_rate +
        0.4 * captcha_rate +
        0.2 * (stats["failure_rate"] * 0.5)  # failures contribute less
    )

    # Clamp
    raw_score = min(1.0, max(0.0, raw_score))

    # Exponential moving average smoothing (alpha=0.3)
    redis = get_redis()
    prev = float(await redis.get(BAN_SCORE_KEY.format(domain=domain)) or 0.0)
    smoothed = prev * 0.7 + raw_score * 0.3

    # Persist
    await redis.set(BAN_SCORE_KEY.format(domain=domain), str(smoothed), ex=3600)

    # Update Prometheus
    metrics.ban_score.labels(domain=domain).set(smoothed)
    metrics.domain_block_rate.labels(domain=domain).set(block_rate)

    if smoothed > 0.3:
        logger.warning(
            "ban_detector.elevated",
            domain=domain,
            ban_score=round(smoothed, 3),
            block_rate=round(block_rate, 3),
            captcha_rate=round(captcha_rate, 3),
        )

    return smoothed


async def get_current_ban_score(domain: str) -> float:
    """Get the latest cached ban score without recomputing."""
    redis = get_redis()
    return float(await redis.get(BAN_SCORE_KEY.format(domain=domain)) or 0.0)


async def get_dangerous_domains(threshold: float = 0.5) -> list[tuple[str, float]]:
    """Return all domains with ban score above threshold."""
    redis = get_redis()
    keys = await redis.keys(BAN_SCORE_KEY.format(domain="*"))
    dangerous = []
    for key in keys:
        domain = key.decode().split(":", 1)[1] if isinstance(key, bytes) else key.split(":", 1)[1]
        score = float(await redis.get(key) or 0.0)
        if score >= threshold:
            dangerous.append((domain, score))
    dangerous.sort(key=lambda x: x[1], reverse=True)
    return dangerous


async def reset_ban_score(domain: str) -> None:
    """Reset ban score after a successful recovery."""
    redis = get_redis()
    await redis.delete(BAN_SCORE_KEY.format(domain=domain))
    await redis.delete(BAN_WINDOW_KEY.format(domain=domain))
    logger.info("ban_detector.reset", domain=domain)
