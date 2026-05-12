"""OpenTelemetry SDK initialization.

Sets up the OTel SDK with OTLP exporter for distributed tracing.
All spans are correlated across the entire request lifecycle:
Scheduler → Kafka → Worker → Network → Extractor → Storage.
"""

from __future__ import annotations

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider, sampling
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from pachong.core.settings import TracingSettings

logger = structlog.get_logger(__name__)

_tracer: trace.Tracer | None = None
_initialized = False


def init_tracing(settings: TracingSettings) -> trace.Tracer:
    """Initialize OpenTelemetry with the configured exporter.

    Returns the global tracer instance for creating spans.
    """
    global _tracer, _initialized
    if _initialized:
        return _tracer

    if not settings.enabled:
        _tracer = trace.get_tracer(settings.service_name)
        _initialized = True
        return _tracer

    resource = Resource.create({SERVICE_NAME: settings.service_name})

    # Configure sampling
    sampler = sampling.TraceIdRatioBased(settings.sample_rate) if settings.sample_rate < 1.0 else sampling.ALWAYS_ON

    provider = TracerProvider(resource=resource, sampler=sampler)

    # Configure exporter
    if settings.exporter == "otlp":
        from pachong.tracing.exporters import get_otlp_exporter

        exporter = get_otlp_exporter(settings)
        if exporter:
            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)

    _tracer = trace.get_tracer(settings.service_name)
    _initialized = True
    logger.info("tracing.initialized", service=settings.service_name, exporter=settings.exporter)
    return _tracer


def get_tracer(name: str = "pachong") -> trace.Tracer:
    """Get a tracer instance. Initializes with defaults if not yet configured."""
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer(name)
    return _tracer
