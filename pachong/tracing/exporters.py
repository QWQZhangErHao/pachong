"""OpenTelemetry exporter configuration.

Supports OTLP (gRPC and HTTP) exporters for sending traces to
Jaeger, Grafana Tempo, or any OTLP-compatible backend.
"""

from __future__ import annotations

import structlog

from pachong.core.settings import TracingSettings

logger = structlog.get_logger(__name__)


def get_otlp_exporter(settings: TracingSettings):
    """Create an OTLP exporter based on configuration.

    Tries gRPC first (better performance), falls back to HTTP.
    """
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPExporter

        exporter = OTLPExporter(endpoint=settings.otlp_endpoint, insecure=True)
        logger.info("tracing.otlp_grpc", endpoint=settings.otlp_endpoint)
        return exporter
    except Exception:
        pass

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHttpExporter

        exporter = OTLPHttpExporter(endpoint=f"{settings.otlp_endpoint}/v1/traces")
        logger.info("tracing.otlp_http", endpoint=settings.otlp_endpoint)
        return exporter
    except Exception as e:
        logger.warning("tracing.otlp_failed", error=str(e))
        return None
