"""Span helpers for creating and managing request-level tracing spans.

Spans track the full request lifecycle through the distributed system.
Each phase of the pipeline creates a child span under the root request span.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from pachong.tracing.setup import get_tracer

# ── Span attributes ──────────────────────────────────────────────────────────

SPAN_ATTR_TASK_ID = "pachong.task_id"
SPAN_ATTR_DOMAIN = "pachong.domain"
SPAN_ATTR_URL = "pachong.url"
SPAN_ATTR_ENGINE = "pachong.engine"
SPAN_ATTR_PROXY_ID = "pachong.proxy_id"
SPAN_ATTR_IDENTITY_ID = "pachong.identity_id"
SPAN_ATTR_STATUS_CODE = "pachong.status_code"
SPAN_ATTR_LATENCY_MS = "pachong.latency_ms"
SPAN_ATTR_CHALLENGE_TYPE = "pachong.challenge_type"
SPAN_ATTR_BAN_SCORE = "pachong.ban_score"
SPAN_ATTR_EXTRACTOR = "pachong.extractor"
SPAN_ATTR_RETRY_COUNT = "pachong.retry_count"


@asynccontextmanager
async def request_span(
    task_id: str,
    url: str,
    domain: str,
    attributes: dict[str, Any] | None = None,
):
    """Root span for a complete request lifecycle.

    Usage:
        async with request_span(task_id, url, domain) as span:
            span.set_attribute("pachong.priority", 80)
            # ... do work ...
    """
    tracer = get_tracer()
    span_name = f"crawl:{domain}"
    span = tracer.start_span(span_name, kind=SpanKind.CONSUMER)

    span.set_attribute(SPAN_ATTR_TASK_ID, task_id)
    span.set_attribute(SPAN_ATTR_URL, url)
    span.set_attribute(SPAN_ATTR_DOMAIN, domain)

    if attributes:
        for k, v in attributes.items():
            span.set_attribute(k, v)

    start = time.monotonic()
    try:
        yield span
        span.set_status(Status(StatusCode.OK))
    except Exception as e:
        span.set_status(Status(StatusCode.ERROR, str(e)))
        span.record_exception(e)
        raise
    finally:
        span.set_attribute(SPAN_ATTR_LATENCY_MS, (time.monotonic() - start) * 1000)
        span.end()


@asynccontextmanager
async def network_span(parent: Span, engine: str, url: str):
    """Span for the network request phase."""
    tracer = get_tracer()
    with tracer.start_as_current_span(
        f"network:{engine}",
        kind=SpanKind.CLIENT,
    ) as span:
        span.set_attribute(SPAN_ATTR_ENGINE, engine)
        span.set_attribute(SPAN_ATTR_URL, url)
        start = time.monotonic()
        try:
            yield span
        finally:
            span.set_attribute(SPAN_ATTR_LATENCY_MS, (time.monotonic() - start) * 1000)


@asynccontextmanager
async def extractor_span(parent: Span, extractor: str):
    """Span for the extraction phase."""
    tracer = get_tracer()
    with tracer.start_as_current_span(
        f"extract:{extractor}",
        kind=SpanKind.INTERNAL,
    ) as span:
        span.set_attribute(SPAN_ATTR_EXTRACTOR, extractor)
        start = time.monotonic()
        try:
            yield span
        finally:
            span.set_attribute(SPAN_ATTR_LATENCY_MS, (time.monotonic() - start) * 1000)


@asynccontextmanager
async def storage_span(parent: Span, backend: str, key: str = ""):
    """Span for storage operations (S3, Postgres, Mongo, Redis)."""
    tracer = get_tracer()
    with tracer.start_as_current_span(
        f"storage:{backend}",
        kind=SpanKind.CLIENT,
    ) as span:
        if key:
            span.set_attribute("pachong.storage_key", key)
        start = time.monotonic()
        try:
            yield span
        finally:
            span.set_attribute(SPAN_ATTR_LATENCY_MS, (time.monotonic() - start) * 1000)


def get_current_span() -> Span | None:
    """Get the currently active OpenTelemetry span."""
    return trace.get_current_span()
