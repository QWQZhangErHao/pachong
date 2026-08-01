"""Proxy rotation strategies.

RoundRobin: simple cycling through available proxies.
Weighted: weighted by success_rate (higher = more frequent).
Bandit: delegates to the bandit module for optimal selection.
"""

from __future__ import annotations

import asyncio
import random

import structlog

from pachong.anti_detect.bandit.environment import BanditEnvironment
from pachong.anti_detect.bandit.policies import select_arm, update_arm
from pachong.anti_detect.proxy.pool import get_active_proxies, get_proxy
from pachong.core.models import ProxyRecord

logger = structlog.get_logger(__name__)


class ProxyRotator:
    """Manages proxy selection using configurable rotation strategies."""

    def __init__(self, strategy: str = "bandit") -> None:
        self.strategy = strategy
        self._round_robin_index = 0
        self._bandit_env = BanditEnvironment()
        self._lock = asyncio.Lock()

    async def select_proxy(
        self,
        region: str | None = None,
        min_success_rate: float = 0.3,
    ) -> ProxyRecord | None:
        """Select the best proxy according to the configured strategy.

        Returns None if no suitable proxy is available.
        """
        proxy_ids = await get_active_proxies(
            min_success_rate=min_success_rate,
            region=region,
            limit=50,
        )

        if not proxy_ids:
            logger.warning("proxy.pool_exhausted", region=region)
            return None

        # Ensure bandit arms exist
        for pid in proxy_ids:
            self._bandit_env.add_arm(pid)

        selected_id: str | None = None

        if self.strategy == "round_robin":
            selected_id = await self._round_robin(proxy_ids)
        elif self.strategy == "weighted":
            selected_id = await self._weighted(proxy_ids)
        elif self.strategy == "bandit":
            selected_id = select_arm(self._bandit_env, algorithm="thompson")

        if not selected_id:
            selected_id = proxy_ids[0]  # Fallback

        return await get_proxy(selected_id)

    async def feedback(
        self,
        proxy_id: str,
        success: bool,
        ban_hit: bool = False,
    ) -> None:
        """Report outcome back to the rotator for strategy optimization."""
        update_arm(self._bandit_env, proxy_id, success=success, ban_hit=ban_hit)

    async def _round_robin(self, proxy_ids: list[str]) -> str:
        async with self._lock:
            idx = self._round_robin_index % len(proxy_ids)
            self._round_robin_index += 1
            return proxy_ids[idx]

    async def _weighted(self, proxy_ids: list[str]) -> str:
        """Weighted random selection based on success rate."""
        proxies = []
        weights = []
        for pid in proxy_ids:
            proxy = await get_proxy(pid)
            if proxy:
                proxies.append(pid)
                weights.append(proxy.success_rate)

        if not proxies:
            return proxy_ids[0]

        # Normalize weights
        total = sum(weights)
        probs = [w / total for w in weights]
        return random.choices(proxies, weights=probs, k=1)[0]

    def get_stats(self) -> dict:
        return self._bandit_env.get_stats()
