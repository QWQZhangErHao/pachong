"""Kafka implementation using aiokafka with Round-Robin partitioning.

Tasks are evenly distributed across partitions (no domain-hash keying).
Per-domain rate control happens in the Worker via Redis token bucket, NOT
by routing same-domain tasks to the same partition.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError

from pachong.core.models import ResultMessage, TaskMessage
from pachong.core.settings import QueueSettings
from pachong.queue.base import AbstractQueue
from pachong.queue.schemas import (
    TOPIC_RESULTS,
    deserialize_result,
    deserialize_task,
    serialize_result,
    serialize_task,
)

logger = structlog.get_logger(__name__)


class KafkaQueue(AbstractQueue):
    """aiokafka-based queue with Round-Robin task distribution."""

    def __init__(self, settings: QueueSettings) -> None:
        self.settings = settings
        self._producer: AIOKafkaProducer | None = None
        self._consumer: AIOKafkaConsumer | None = None
        self._last_batch_offset: dict[int, int] = {}

    async def connect(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=",".join(self.settings.kafka_brokers),
            compression_type="lz4",
            acks="all",
            max_in_flight_requests_per_connection=5,
        )
        await self._producer.start()
        logger.info("kafka.producer.connected", brokers=self.settings.kafka_brokers)

    async def close(self) -> None:
        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()
        logger.info("kafka.disconnected")

    async def publish_task(self, topic: str, message: TaskMessage) -> None:
        """Publish task with Round-Robin partitioning (no key = random partition)."""
        if not self._producer:
            raise RuntimeError("Kafka producer not connected")
        payload = serialize_task(message)
        await self._producer.send_and_wait(topic, value=payload)
        logger.debug(
            "kafka.task.published",
            topic=topic,
            task_id=str(message.task_id),
            domain=message.domain,
        )

    async def publish_result(self, message: ResultMessage) -> None:
        if not self._producer:
            raise RuntimeError("Kafka producer not connected")
        payload = serialize_result(message)
        await self._producer.send_and_wait(TOPIC_RESULTS, value=payload)
        logger.debug("kafka.result.published", task_id=str(message.task_id))

    async def subscribe(self, topics: list[str]) -> AsyncIterator[TaskMessage]:
        """Subscribe to task topics and yield deserialized TaskMessages."""
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=",".join(self.settings.kafka_brokers),
            group_id=self.settings.consumer_group,
            max_poll_records=self.settings.max_poll_records,
            session_timeout_ms=self.settings.session_timeout_ms,
            heartbeat_interval_ms=self.settings.heartbeat_interval_ms,
            enable_auto_commit=False,  # Manual commit after processing
            auto_offset_reset="earliest",
        )
        await self._consumer.start()
        logger.info("kafka.consumer.started", topics=topics, group=self.settings.consumer_group)

        try:
            async for batch in self._consumer:
                for topic_partition, messages in batch.items():
                    for msg in messages:
                        try:
                            task = deserialize_task(msg.value)
                            self._last_batch_offset[msg.partition] = msg.offset
                            yield task
                        except Exception:
                            logger.exception("kafka.deserialize.failed", partition=msg.partition)
                            continue
        finally:
            await self._consumer.stop()
            self._consumer = None

    async def commit(self) -> None:
        """Commit offsets for the last consumed batch."""
        if self._consumer and self._last_batch_offset:
            await self._consumer.commit()
            self._last_batch_offset.clear()

    async def healthy(self) -> bool:
        try:
            if self._producer:
                await self._producer.partitions_for(TOPIC_RESULTS)
            return True
        except KafkaError:
            return False

    async def queue_depth(self, topic: str) -> int:
        """Approximate queue depth via Kafka consumer offsets.

        Returns -1 if metadata is unavailable.
        """
        if not self._consumer:
            return -1
        try:
            partitions = self._consumer.partitions_for_topic(topic)
            if not partitions:
                return 0
            total = 0
            for p in partitions:
                end_offset = await self._consumer.end_offsets([p])
                committed = await self._consumer.committed(p)
                if committed is not None:
                    total += end_offset[p] - committed
            return total
        except KafkaError:
            return -1
