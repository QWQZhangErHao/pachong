"""Pointer-based serverless payload builder.

CRITICAL DESIGN: Never send raw HTML/DOM in the serverless payload.
Cloud providers impose a ~6MB request body limit. Instead, we pass S3
pointers, and the function fetches data directly from object storage.

Payload schema (maximum ~500 bytes):
{
    "task_id": "uuid",
    "s3_bucket": "pachong-raw",
    "s3_raw_html_key": "raw/2024/05/09/abc.html",
    "s3_screenshot_key": "screenshots/2024/05/09/abc.png",
    "extraction_rules": [...],  // Pre-cached rules (optional, <5KB)
    "callback_topic": "pachong.results"
}
"""

from __future__ import annotations

import uuid

from pachong.core.models import ExtractionRule, ServerlessPayload


def build_payload(
    task_id: uuid.UUID,
    s3_bucket: str,
    s3_raw_html_key: str,
    s3_screenshot_key: str | None = None,
    extraction_rules: list[ExtractionRule] | None = None,
    callback_topic: str = "pachong.results",
) -> ServerlessPayload:
    """Build a compact pointer-based payload for serverless invocation.

    This payload is ~200-500 bytes, well under the 6MB cloud function
    request body limit.
    """
    return ServerlessPayload(
        task_id=task_id,
        s3_bucket=s3_bucket,
        s3_raw_html_key=s3_raw_html_key,
        s3_screenshot_key=s3_screenshot_key,
        extraction_rules=[r.model_dump() for r in extraction_rules] if extraction_rules else [],
        callback_topic=callback_topic,
    )


def serialize_payload(payload: ServerlessPayload) -> bytes:
    """Serialize to JSON bytes for HTTP invocation."""
    return payload.model_dump_json(exclude_none=True).encode("utf-8")


def deserialize_payload(data: bytes | str) -> ServerlessPayload:
    """Deserialize from JSON bytes or string."""
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return ServerlessPayload.model_validate_json(data)


def validate_payload_size(payload: ServerlessPayload, max_bytes: int = 5_000_000) -> bool:
    """Ensure payload is within cloud function limits."""
    size = len(serialize_payload(payload))
    return size <= max_bytes


class ServerlessPayloadBuilder:
    """Fluent builder for serverless payloads."""

    def __init__(self, s3_bucket: str) -> None:
        self._bucket = s3_bucket
        self._task_id: uuid.UUID | None = None
        self._html_key: str | None = None
        self._screenshot_key: str | None = None
        self._rules: list[ExtractionRule] = []

    def with_task(self, task_id: uuid.UUID) -> ServerlessPayloadBuilder:
        self._task_id = task_id
        return self

    def with_html(self, s3_key: str) -> ServerlessPayloadBuilder:
        self._html_key = s3_key
        return self

    def with_screenshot(self, s3_key: str) -> ServerlessPayloadBuilder:
        self._screenshot_key = s3_key
        return self

    def with_rules(self, rules: list[ExtractionRule]) -> ServerlessPayloadBuilder:
        self._rules = rules
        return self

    def build(self) -> ServerlessPayload:
        if not self._task_id or not self._html_key:
            raise ValueError("task_id and html_key are required")

        return build_payload(
            task_id=self._task_id,
            s3_bucket=self._bucket,
            s3_raw_html_key=self._html_key,
            s3_screenshot_key=self._screenshot_key,
            extraction_rules=self._rules if self._rules else None,
        )
