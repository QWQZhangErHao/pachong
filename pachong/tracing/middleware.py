"""Tracing middleware for ASGI (FastAPI) and aiohttp.

Automatically creates spans for incoming HTTP requests to the management API.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from opentelemetry import trace
from opentelemetry.trace import SpanKind


def setup_api_tracing(app: FastAPI) -> None:
    """Add OpenTelemetry tracing middleware to a FastAPI app."""

    @app.middleware("http")
    async def tracing_middleware(request: Request, call_next):
        tracer = trace.get_tracer("pachong.api")

        span_name = f"{request.method} {request.url.path}"
        with tracer.start_as_current_span(
            span_name,
            kind=SpanKind.SERVER,
        ) as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.host", request.url.hostname or "")
            span.set_attribute("http.client_ip", request.client.host if request.client else "")

            response = await call_next(request)

            span.set_attribute("http.status_code", response.status_code)
            return response
