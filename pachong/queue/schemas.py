"""Wire-format message schemas for Kafka."""

from __future__ import annotations

from pachong.core.models import ResultMessage, TaskMessage

# Topic naming convention
TOPIC_TASKS_HIGH = "pachong.tasks.high"
TOPIC_TASKS_NORMAL = "pachong.tasks.normal"
TOPIC_TASKS_LOW = "pachong.tasks.low"
TOPIC_TASKS_DEFERRED = "pachong.tasks.deferred"  # Rate-limited tasks retry queue
TOPIC_RESULTS = "pachong.results"
TOPIC_DEAD_LETTER = "pachong.dead_letter"

ALL_TASK_TOPICS = [TOPIC_TASKS_HIGH, TOPIC_TASKS_NORMAL, TOPIC_TASKS_LOW]


def priority_to_topic(priority: int) -> str:
    """Map numeric priority (0-100) to Kafka topic."""
    if priority >= 70:
        return TOPIC_TASKS_HIGH
    elif priority >= 30:
        return TOPIC_TASKS_NORMAL
    return TOPIC_TASKS_LOW


def serialize_task(msg: TaskMessage) -> bytes:
    """Serialize a TaskMessage to JSON bytes for Kafka."""
    return msg.model_dump_json().encode("utf-8")


def deserialize_task(data: bytes) -> TaskMessage:
    """Deserialize JSON bytes from Kafka back to TaskMessage."""
    return TaskMessage.model_validate_json(data.decode("utf-8"))


def serialize_result(msg: ResultMessage) -> bytes:
    """Serialize a ResultMessage to JSON bytes."""
    return msg.model_dump_json().encode("utf-8")


def deserialize_result(data: bytes) -> ResultMessage:
    """Deserialize JSON bytes back to ResultMessage."""
    return ResultMessage.model_validate_json(data.decode("utf-8"))
