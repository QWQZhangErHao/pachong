"""Bandit policies: Thompson Sampling, UCB, Exp3.

Thompson Sampling (Beta-Bernoulli): best for stationary or slowly-changing
reward distributions. Recommended default for proxy/identity selection.

UCB (Upper Confidence Bound): more deterministic, optimistically explores
under-tested arms. Good for initial proxy pool exploration.

Exp3 (Exponential-weight algorithm for Exploration and Exploitation):
best for adversarial settings where the environment is actively hostile.
Use when target sites are aggressively rotating anti-bot countermeasures.
"""

from __future__ import annotations

import math
import random

from pachong.anti_detect.bandit.environment import ArmState, BanditEnvironment


def thompson_sampling(env: BanditEnvironment) -> str | None:
    """Select an arm using Thompson Sampling.

    For each arm, sample from Beta(α, β). Choose the arm with the
    highest sample. This naturally balances exploration vs exploitation:
    arms with few trials have wide Beta distributions → higher chance
    of getting a favorable sample.
    """
    if not env.arms:
        return None

    samples: list[tuple[str, float]] = []
    for arm_id, arm in env.arms.items():
        # Skip banned arms
        if arm.ban_rate >= 0.5:
            continue

        # Thompson sample from Beta distribution
        # Beta(α, β) where α = successes+1, β = failures+1
        sample = random.betavariate(arm.alpha, arm.beta)
        samples.append((arm_id, sample))

    if not samples:
        return None

    # Epsilon-greedy: occasionally pick random for forced exploration
    if random.random() < env.exploration_rate:
        return random.choice(samples)[0]

    return max(samples, key=lambda x: x[1])[0]


def ucb_select(env: BanditEnvironment, c: float = 2.0) -> str | None:
    """Select an arm using UCB1 (Upper Confidence Bound).

    UCB = estimated_reward + c * sqrt(ln(total_trials) / arm_trials)

    The exploration bonus shrinks as an arm accumulates trials.
    """
    if not env.arms:
        return None

    total_trials = sum(a.trials for a in env.arms.values()) + 1

    best_arm: str | None = None
    best_ucb = float("-inf")

    for arm_id, arm in env.arms.items():
        if arm.ban_rate >= 0.5:
            continue

        if arm.trials == 0:
            return arm_id  # Always explore untried arms

        # UCB formula
        exploration_bonus = c * math.sqrt(math.log(total_trials) / arm.trials)
        ucb = arm.estimated_reward + exploration_bonus

        if ucb > best_ucb:
            best_ucb = ucb
            best_arm = arm_id

    return best_arm


def exp3_select(
    env: BanditEnvironment,
    gamma: float = 0.1,
) -> str | None:
    """Select an arm using Exp3 (adversarial bandit).

    Exp3 assigns weights to arms and updates them multiplicatively
    based on observed rewards. It's robust against adversarial
    reward distributions — ideal when target sites are actively
    trying to detect and block scraping patterns.

    γ (gamma): exploration parameter. Higher = more exploration.
    """
    if not env.arms:
        return None

    active_arms = [arm_id for arm_id, arm in env.arms.items() if arm.ban_rate < 0.5]
    if not active_arms:
        return None

    n = len(active_arms)

    # Get weights (use inverse of ban_rate as weight)
    weights = []
    for arm_id in active_arms:
        arm = env.arms[arm_id]
        # Weight = estimated_reward, but penalize banned arms
        w = arm.estimated_reward * (1 - arm.ban_rate)
        weights.append(max(0.001, w))  # Minimum weight to avoid zero

    total_weight = sum(weights)

    # Compute probabilities with uniform exploration
    probabilities = [
        (1 - gamma) * w / total_weight + gamma / n
        for w in weights
    ]

    # Weighted random selection
    r = random.random()
    cumulative = 0.0
    for arm_id, prob in zip(active_arms, probabilities):
        cumulative += prob
        if r <= cumulative:
            return arm_id

    return active_arms[-1]


# ── Convenience ──────────────────────────────────────────────────────────────


def select_arm(
    env: BanditEnvironment,
    algorithm: str = "thompson",
) -> str | None:
    """Select an arm using the specified algorithm."""
    algorithms = {
        "thompson": thompson_sampling,
        "ucb": ucb_select,
        "exp3": exp3_select,
    }
    selector = algorithms.get(algorithm, thompson_sampling)
    return selector(env)


def update_arm(
    env: BanditEnvironment,
    arm_id: str,
    success: bool,
    ban_hit: bool = False,
) -> None:
    """Record feedback for an arm after use."""
    arm = env.get_arm(arm_id)
    if not arm:
        env.add_arm(arm_id)
        arm = env.get_arm(arm_id)

    if arm:
        reward = 1.0 if success else 0.0
        arm.record_reward(reward)
        if ban_hit:
            arm.record_ban()
