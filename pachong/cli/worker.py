"""Worker process — consumes tasks from Kafka, enforces Redis rate limits.

Key logic (matching the architecture blueprint):
1. Pull task from Kafka (Round-Robin distribution)
2. Request Redis token bucket for this domain
3. No token → defer task to retry queue with exponential backoff
4. Got token → execute request (stub, Phase 3 adds network engine)
5. Commit Kafka offset after successful processing
"""

from __future__ import annotations

import asyncio
import uuid

import structlog

from pachong.core.models import TaskMessage, TaskStatus
from pachong.core.settings import Settings
from pachong.queue.backpressure import get_domain_token, record_failure, record_success
from pachong.queue.kafka import KafkaQueue
from pachong.queue.schemas import ALL_TASK_TOPICS, priority_to_topic
from pachong.scheduler.rate_limiter import get_domain_qps, try_acquire_token, wait_for_token

logger = structlog.get_logger(__name__)


class WorkerEngine:
    """Worker that consumes tasks, enforces rate limits, and executes requests."""

    def __init__(self, settings: Settings, worker_id: str | None = None) -> None:
        self.settings = settings
        self.worker_id = worker_id or str(uuid.uuid4())[:8]
        self.queue = KafkaQueue(settings.queue)
        self._running = False
        self._tasks_processed = 0
        self._tasks_failed = 0
        self._tasks_deferred = 0

    async def start(self) -> None:
        await self.queue.connect()
        self._running = True
        logger.info("worker.started", worker_id=self.worker_id)

    async def stop(self) -> None:
        self._running = False
        await self.queue.close()
        logger.info(
            "worker.stopped",
            worker_id=self.worker_id,
            processed=self._tasks_processed,
            failed=self._tasks_failed,
            deferred=self._tasks_deferred,
        )

    async def run(self) -> None:
        await self.start()
        try:
            async for task in self.queue.subscribe(ALL_TASK_TOPICS):
                if not self._running:
                    break
                await self._handle_task(task)
        finally:
            await self.stop()

    async def _handle_task(self, msg: TaskMessage) -> None:
        """Process a single task through the rate-limit → execute pipeline."""
        domain = msg.domain

        # Step 1: Apply Redis token bucket (per-domain QPS control)
        qps = await get_domain_qps(domain, self.settings.resilience.default_domain_qps)
        acquired = await try_acquire_token(domain, qps)

        if not acquired:
            # Wait up to 30s for a token
            acquired = await wait_for_token(domain, qps, timeout_ms=30_000)
            if not acquired:
                # Defer the task — re-enqueue to a low-priority deferred topic
                msg.retry_count += 1
                if msg.retry_count <= msg.max_retries:
                    await self.queue.publish_task("pachong.tasks.deferred", msg)
                    self._tasks_deferred += 1
                    logger.debug("worker.deferred", task_id=str(msg.task_id), domain=domain)
                else:
                    logger.warning(
                        "worker.max_retries_exceeded",
                        task_id=str(msg.task_id),
                        domain=domain,
                    )
                    self._tasks_failed += 1
                return

        # Step 2: Execute the request (stub — Phase 3 will add real network engine)
        try:
            await self._execute(msg)
            self._tasks_processed += 1
            await record_success(domain)
            logger.info(
                "worker.task_done",
                task_id=str(msg.task_id),
                domain=domain,
                processed=self._tasks_processed,
            )
        except Exception:
            self._tasks_failed += 1
            await record_failure(domain)
            logger.exception("worker.task_failed", task_id=str(msg.task_id), domain=domain)

            # Re-enqueue if retries remain
            msg.retry_count += 1
            if msg.retry_count <= msg.max_retries:
                await self.queue.publish_task("pachong.tasks.low", msg)

    async def _execute(self, msg: TaskMessage) -> None:
        """Execute the actual HTTP request. Stub — Phase 3 replaces this with the network engine."""
        # Simulate work
        await asyncio.sleep(0.01)
        # Phase 3 will:
        #   1. Select engine via AdaptiveEngineSelector
        #   2. Fetch identity from anti_detect
        #   3. Execute request
        #   4. Run extractor pipeline
        #   5. Store results to S3 + MongoDB + Postgres
        pass


async def run_worker(settings: Settings) -> None:
    engine = WorkerEngine(settings)
    await engine.run()
