"""Serverless dispatcher — monitors Kafka queue depth and offloads to
serverless functions when the queue exceeds the configured threshold.

This enables elastic scaling: the core worker cluster handles baseline
load, and serverless functions absorb traffic spikes (Black Friday, etc.).
"""

from __future__ import annotations

import asyncio

import structlog

from pachong.core.settings import ServerlessSettings
from pachong.serverless.local import LocalServerlessRunner

logger = structlog.get_logger(__name__)


class ServerlessDispatcher:
    """Monitors queue depth and dispatches overflow to serverless functions.

    Polls Kafka consumer group lag at regular intervals. When lag exceeds
    the threshold, builds pointer-based payloads and invokes serverless
    functions until the backlog is cleared or max concurrency is reached.
    """

    def __init__(self, settings: ServerlessSettings) -> None:
        self.settings = settings
        self._runner = self._create_runner()
        self._running = False
        self._dispatched_total = 0

    def _create_runner(self) -> LocalServerlessRunner:
        if self.settings.provider == "local":
            return LocalServerlessRunner(max_concurrency=self.settings.max_concurrent_functions)
        elif self.settings.provider == "aws":
            # Future: AWS Lambda runner
            return LocalServerlessRunner(max_concurrency=self.settings.max_concurrent_functions)
        elif self.settings.provider == "gcp":
            # Future: GCP Cloud Functions runner
            return LocalServerlessRunner(max_concurrency=self.settings.max_concurrent_functions)
        else:
            return LocalServerlessRunner(max_concurrency=self.settings.max_concurrent_functions)

    async def start(self) -> None:
        self._running = True
        logger.info("serverless.dispatcher.started", provider=self.settings.provider)

    async def stop(self) -> None:
        self._running = False
        logger.info("serverless.dispatcher.stopped", total_dispatched=self._dispatched_total)

    async def should_dispatch(self, queue_depth: int) -> bool:
        """Determine if serverless offloading should be activated.

        Returns True when:
        - Serverless is enabled
        - Queue depth exceeds threshold
        - We have available function concurrency
        """
        if not self.settings.enabled:
            return False
        if queue_depth < self.settings.dispatch_queue_depth_threshold:
            return False
        if self._runner.active_invocations >= self._runner.max_concurrency:
            return False
        return True

    async def dispatch_if_needed(self, queue_depth: int) -> int:
        """Check conditions and dispatch if needed. Returns number dispatched.

        In production, this reads pending tasks from Kafka, builds S3-pointer
        payloads, and invokes serverless functions. For now, it's a framework
        ready for integration.
        """
        if not await self.should_dispatch(queue_depth):
            return 0

        # Calculate how many to dispatch
        available = self._runner.max_concurrency - self._runner.active_invocations
        excess = max(0, queue_depth - self.settings.dispatch_queue_depth_threshold)
        to_dispatch = min(available, excess, self.settings.max_concurrent_functions)

        if to_dispatch <= 0:
            return 0

        logger.info(
            "serverless.dispatching",
            queue_depth=queue_depth,
            to_dispatch=to_dispatch,
            active=self._runner.active_invocations,
        )

        # In a real implementation, this would:
        # 1. Read tasks from Kafka (peek, don't commit)
        # 2. Check S3 has the raw HTML for each task
        # 3. Build pointer payloads
        # 4. Invoke serverless functions
        # 5. Commits offsets after serverless confirms processing

        # For now, return the count we would dispatch
        self._dispatched_total += to_dispatch
        return to_dispatch

    async def run(self, poll_interval_ms: int = 5000) -> None:
        """Main dispatcher loop — polls queue depth and dispatches as needed.

        In a production deployment, this runs alongside the scheduler.
        """
        await self.start()
        try:
            while self._running:
                try:
                    # Get queue depth from Kafka
                    # (In production, this reads from Kafka consumer group lag)
                    # For now, placeholder
                    queue_depth = 0

                    dispatched = await self.dispatch_if_needed(queue_depth)
                    if dispatched > 0:
                        logger.info("serverless.dispatched", count=dispatched)

                except Exception:
                    logger.exception("serverless.loop_error")

                await asyncio.sleep(poll_interval_ms / 1000)
        finally:
            await self.stop()

    @property
    def total_dispatched(self) -> int:
        return self._dispatched_total
