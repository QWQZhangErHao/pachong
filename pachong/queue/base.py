"""Abstract message queue interface.

Allows swapping Kafka for RabbitMQ or an in-memory stub for testing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pachong.core.models import ResultMessage, TaskMessage


class AbstractQueue(ABC):
    """Asynchronous message queue abstraction for task dispatch and result collection."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the broker."""

    @abstractmethod
    async def close(self) -> None:
        """Gracefully close connections."""

    @abstractmethod
    async def publish_task(self, topic: str, message: TaskMessage) -> None:
        """Publish a task to a topic."""

    @abstractmethod
    async def publish_result(self, message: ResultMessage) -> None:
        """Publish a processing result."""

    @abstractmethod
    async def subscribe(self, topics: list[str]) -> AsyncIterator[TaskMessage]:
        """Subscribe to task topics and yield messages.

        The consumer must call commit() after successful processing.
        """

    @abstractmethod
    async def commit(self) -> None:
        """Commit offsets for the last batch of consumed messages."""

    @abstractmethod
    async def healthy(self) -> bool:
        """Health check — returns True if broker is reachable."""

    @abstractmethod
    async def queue_depth(self, topic: str) -> int:
        """Return approximate number of pending messages in a topic."""
