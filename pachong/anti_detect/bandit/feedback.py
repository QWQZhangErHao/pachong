"""Reward signal computation from scraping outcomes.

Converts raw scraping results (status codes, timing, extraction success)
into normalized reward signals [0.0-1.0] for the bandit algorithms.

High reward = good proxy+identity combo that works against target site.
Low reward = blocked, detected, or poor performance.
"""

from __future__ import annotations

import math

from pachong.network.response import FetchResponse


def compute_reward(response: FetchResponse, extraction_success: bool = True) -> float:
    """Compute a reward signal [0.0-1.0] from a scraping attempt.

    Reward components:
    - Status code: 200 = +0.5, 3xx = +0.3, 4xx = +0.1, 5xx = 0.0
    - Speed bonus: fast responses get extra reward
    - Blocking penalty: JS challenges and anti-bot blocks get 0
    - Extraction bonus: successful data extraction adds +0.2
    """
    reward = 0.0

    # Status code component
    if 200 <= response.status_code < 300:
        reward += 0.5
    elif 300 <= response.status_code < 400:
        reward += 0.3
    elif 400 <= response.status_code < 500:
        reward += 0.1
        if response.status_code == 403:
            reward -= 0.2
        if response.status_code == 429:
            reward -= 0.1
    else:
        reward += 0.0

    # Anti-bot detection penalty
    if response.is_js_challenge:
        if response.js_challenge_type == "cloudflare":
            reward -= 0.5
        elif response.js_challenge_type == "akamai":
            reward -= 0.4
        elif response.js_challenge_type == "datadome":
            reward -= 0.5
        elif response.js_challenge_type == "captcha":
            reward -= 0.6

    if response.is_blocked:
        reward -= 0.3

    # Speed component
    if response.timing.total_ms > 0:
        speed_score: float = 0.0
        if response.timing.total_ms < 1000:
            speed_score = 0.2
        elif response.timing.total_ms < 3000:
            speed_score = 0.15
        elif response.timing.total_ms < 5000:
            speed_score = 0.1
        elif response.timing.total_ms < 10000:
            speed_score = 0.05
        reward += speed_score

    # Extraction success bonus
    if extraction_success and response.is_success:
        reward += 0.2

    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, reward))


def is_successful(reward: float, threshold: float = 0.5) -> bool:
    """Determine if a reward qualifies as success for the bandit."""
    return reward >= threshold


def compute_domain_reward(
    responses: list[FetchResponse],
    extraction_success_rate: float = 1.0,
) -> float:
    """Compute aggregate reward for a domain from multiple responses.

    Used by the scheduler and resilience modules to track domain health.
    """
    if not responses:
        return 0.5

    rewards = [compute_reward(r) for r in responses]
    avg = sum(rewards) / len(rewards)

    # Penalize high variance (inconsistent results = sign of anti-bot)
    if len(rewards) > 1:
        variance = sum((r - avg) ** 2 for r in rewards) / len(rewards)
        variance_penalty = min(0.2, math.sqrt(variance) * 0.5)
        avg -= variance_penalty

    # Incorporate extraction success
    avg = avg * 0.7 + extraction_success_rate * 0.3

    return max(0.0, min(1.0, avg))


def compute_ban_indicator(response: FetchResponse) -> float:
    """Compute a ban probability indicator [0.0-1.0] from a single response.

    This is the primary input signal for the ban_detector (Phase 6).
    """
    ban_score = 0.0

    # Explicit blocks
    if response.status_code == 403:
        ban_score = max(ban_score, 0.8)
    if response.status_code == 429:
        ban_score = max(ban_score, 0.5)

    # JS challenge detected
    if response.is_js_challenge:
        if response.js_challenge_type in ("cloudflare", "datadome"):
            ban_score = max(ban_score, 0.9)
        elif response.js_challenge_type == "akamai":
            ban_score = max(ban_score, 0.8)
        elif response.js_challenge_type in ("captcha", "recaptcha", "hcaptcha"):
            ban_score = max(ban_score, 0.95)

    # Suspicious blank page
    if response.status_code == 200 and response.js_challenge_type == "suspicious_blank":
        ban_score = max(ban_score, 0.7)

    return ban_score
