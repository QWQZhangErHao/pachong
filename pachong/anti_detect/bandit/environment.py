"""Multi-Armed Bandit environment for proxy/identity selection.

Arms = proxies or identities. The environment tracks each arm's
performance history and provides the interface for bandit policies
to select the best arms while exploring new ones.

Adversarial variant: target sites actively try to detect and block
patterns, so the reward distribution is non-stationary. We use
discounted rewards to track recent performance more heavily.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field


@dataclass
class ArmState:
    """State of a single bandit arm (proxy or identity)."""

    arm_id: str
    trials: int = 0
    successes: int = 0
    failures: int = 0
    ban_hits: int = 0
    estimated_reward: float = 0.5  # Beta distribution mean
    alpha: float = 1.0  # Beta(α, β) — successes + 1
    beta: float = 1.0   # Beta(α, β) — failures + 1
    last_used: float = 0.0
    reward_history: list[tuple[float, float]] = field(default_factory=list)  # (reward, timestamp)

    @property
    def success_rate(self) -> float:
        return self.successes / max(1, self.trials)

    @property
    def ban_rate(self) -> float:
        return self.ban_hits / max(1, self.trials)

    def record_reward(self, reward: float, timestamp: float | None = None) -> None:
        self.trials += 1
        self.last_used = timestamp or time.time()

        if reward > 0.5:
            self.successes += 1
            self.alpha += reward
        else:
            self.failures += 1
            self.beta += (1 - reward)

        # Discounted exponential moving average
        self.estimated_reward = self.alpha / (self.alpha + self.beta)

        # Keep reward history bounded
        self.reward_history.append((reward, self.last_used))
        if len(self.reward_history) > 100:
            self.reward_history = self.reward_history[-50:]

    def record_ban(self) -> None:
        self.ban_hits += 1
        self.record_reward(0.0)


@dataclass
class BanditEnvironment:
    """Manages arms and provides selection context."""

    arms: dict[str, ArmState] = field(default_factory=dict)
    exploration_rate: float = 0.1  # ε-greedy exploration

    def add_arm(self, arm_id: str) -> None:
        if arm_id not in self.arms:
            self.arms[arm_id] = ArmState(arm_id=arm_id)

    def remove_arm(self, arm_id: str) -> None:
        self.arms.pop(arm_id, None)

    def get_arm(self, arm_id: str) -> ArmState | None:
        return self.arms.get(arm_id)

    def get_arm_ids(self) -> list[str]:
        return list(self.arms.keys())

    def get_best_arm(self) -> ArmState | None:
        """Return the arm with highest estimated reward, excluding banned ones."""
        active = [a for a in self.arms.values() if a.ban_rate < 0.5]
        if not active:
            return None
        return max(active, key=lambda a: a.estimated_reward)

    def get_stats(self) -> dict:
        """Return summary statistics for all arms."""
        return {
            "total_arms": len(self.arms),
            "total_trials": sum(a.trials for a in self.arms.values()),
            "total_bans": sum(a.ban_hits for a in self.arms.values()),
            "active_arms": sum(1 for a in self.arms.values() if a.ban_rate < 0.5),
            "best_reward": max((a.estimated_reward for a in self.arms.values()), default=0),
        }
