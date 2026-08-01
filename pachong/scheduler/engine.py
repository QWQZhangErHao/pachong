"""Main scheduler loop.

Reads pending tasks from PostgreSQL, applies priority scoring, politeness
checks, and deduplication, then publishes tasks to Kafka with Round-Robin
partitioning. Per-domain rate control is handled by Workers via Redis tokens.
"""

from __future__ import annotations

import asyncio
import uuid

import structlog

from pachong.core.models import TaskMessage, TaskStatus
from pachong.core.settings import Settings
from pachong.queue.kafka import KafkaQueue
from pachong.queue.schemas import priority_to_topic
from pachong.scheduler.deduplication import check_and_mark
from pachong.scheduler.frontier import can_request, get_domain_delay
from pachong.scheduler.priority import score_url
from pachong.scheduler.rate_limiter import init_domain_config
from pachong.storage.postgres.engine import get_session, init_postgres
from pachong.storage.postgres.models import TaskModel

logger = structlog.get_logger(__name__)


class SchedulerEngine:
    """Main scheduler that feeds tasks from PostgreSQL into Kafka."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.queue = KafkaQueue(settings.queue)
        self._running = False
        self.batch_size = 200
        self.poll_interval_ms = 500  # idle sleep between empty polls

    async def start(self) -> None:
        await init_postgres(self.settings)
        await self.queue.connect()
        self._running = True
        logger.info("scheduler.started")

    async def stop(self) -> None:
        self._running = False
        await self.queue.close()
        logger.info("scheduler.stopped")

    async def run(self) -> None:
        """Main scheduler loop."""
        await self.start()
        try:
            while self._running:
                dispatched = await self._poll_and_dispatch()
                if dispatched == 0:
                    await asyncio.sleep(self.poll_interval_ms / 1000)
        finally:
            await self.stop()

    async def _poll_and_dispatch(self) -> int:
        """Fetch pending tasks and dispatch to Kafka. Returns count dispatched."""
        session = await get_session()
        try:
            from sqlalchemy import select

            stmt = (
                select(TaskModel)
                .where(TaskModel.status == TaskStatus.PENDING.value)
                .order_by(TaskModel.priority.desc())
                .limit(self.batch_size)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        finally:
            await session.close()

        dispatched = 0
        for row in rows:
            if not self._running:
                break

            # 1. Deduplication check
            is_new = await check_and_mark(row.url)
            if not is_new:
                await self._mark_status(session, row.task_id, TaskStatus.QUEUED, "duplicate")
                continue

            # 2. Politeness check via frontier
            domain = row.domain
            min_delay = await get_domain_delay(domain)
            if not await can_request(domain, min_delay):
                continue  # skip for this cycle, will retry next poll

            # 3. Score priority
            priority = score_url(row.url)

            # 4. Ensure rate-limit config exists for domain
            await init_domain_config(domain, self.settings.resilience.default_domain_qps)

            # 5. Build and publish task message
            msg = TaskMessage(
                task_id=row.task_id,
                url=row.url,
                domain=domain,
                priority=priority,
                engine_hint=row.engine_hint,
                headers=row.metadata_.get("headers", {}),
                max_retries=row.max_retries,
            )

            topic = priority_to_topic(priority)
            try:
                await self.queue.publish_task(topic, msg)
                await self._mark_status(session, row.task_id, TaskStatus.QUEUED)
                dispatched += 1
            except Exception:
                logger.exception("scheduler.publish_failed", task_id=str(row.task_id))

        if dispatched:
            logger.info("scheduler.dispatched", count=dispatched)
        return dispatched

    async def _mark_status(self, session, task_id: uuid.UUID, status: TaskStatus, error: str | None = None) -> None:
        from sqlalchemy import update

        values = {"status": status.value}
        if error:
            values["error_message"] = error
        stmt = update(TaskModel).where(TaskModel.task_id == task_id).values(**values)
        try:
            await session.execute(stmt)
            await session.commit()
        except Exception:
            await session.rollback()


async def run_scheduler(settings: Settings) -> None:
    engine = SchedulerEngine(settings)
    await engine.run()
