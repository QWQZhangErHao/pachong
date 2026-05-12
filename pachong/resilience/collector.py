"""Metric collector — tracks success rates, latency, and error patterns.

Aggregates per-domain statistics from task results and feeds them
into Prometheus metrics and the ban_detector.
"""

from __future__ import annotations

import time
from collections import defaultdict

import structlog

from pachong.network.response import FetchResponse
from pachong.resilience import metrics

logger = structlog.get_logger(__name__)

# In-process stat buffers (periodically flushed to Prometheus)
_domain_stats: dict[str, dict] = defaultdict(lambda: {
    "total": 0,
    "success": 0,
    "blocked": 0,
    "captcha": 0,
    "failed": 0,
    "latencies_ms": [],
    "last_flush": time.time(),
})

MAX_LATENCY_SAMPLES = 100


def record_task_result(
    task_id: str,
    domain: str,
    response: FetchResponse,
    engine: str,
    extraction_success: bool = True,
) -> None:
    """Record a single task result for statistics and Prometheus export."""
    stats = _domain_stats[domain]
    stats["total"] += 1

    if response.is_success and not response.is_blocked:
        stats["success"] += 1
        status = "success"
    elif response.is_js_challenge:
        stats["captcha"] += 1
        status = "challenge"
        if response.js_challenge_type:
            metrics.engine_escalations.labels(
                from_engine=engine,
                to_engine="playwright" if engine == "http" else "nodriver",
                reason=response.js_challenge_type,
            ).inc()
    elif response.is_blocked:
        stats["blocked"] += 1
        status = "blocked"
    else:
        stats["failed"] += 1
        status = "failed"

    # Latency
    if response.timing.total_ms > 0:
        stats["latencies_ms"].append(response.timing.total_ms)
        if len(stats["latencies_ms"]) > MAX_LATENCY_SAMPLES:
            stats["latencies_ms"] = stats["latencies_ms"][-MAX_LATENCY_SAMPLES:]

    # Prometheus counters
    metrics.tasks_processed.labels(domain=domain, engine=engine, status=status).inc()
    metrics.task_latency_seconds.labels(domain=domain, engine=engine).observe(
        response.timing.total_ms / 1000
    )

    # HTTP request metrics
    metrics.http_requests_total.labels(
        domain=domain, engine=engine, status_code=str(response.status_code),
    ).inc()
    metrics.http_request_latency_seconds.labels(domain=domain, engine=engine).observe(
        response.timing.total_ms / 1000
    )

    # Extraction
    ext_status = "success" if extraction_success else "failed"
    metrics.extractions_total.labels(domain=domain, strategy="pipeline", status=ext_status).inc()


def get_domain_stats(domain: str) -> dict:
    """Get current stats for a domain."""
    stats = _domain_stats[domain]
    total = max(stats["total"], 1)

    latencies = stats["latencies_ms"]
    p50 = _percentile(latencies, 0.50) if latencies else 0
    p99 = _percentile(latencies, 0.99) if latencies else 0

    return {
        "domain": domain,
        "total": stats["total"],
        "success_rate": stats["success"] / total,
        "block_rate": stats["blocked"] / total,
        "captcha_rate": stats["captcha"] / total,
        "failure_rate": stats["failed"] / total,
        "latency_p50_ms": p50,
        "latency_p99_ms": p99,
        "avg_latency_ms": sum(latencies) / max(len(latencies), 1),
    }


def reset_domain_stats(domain: str) -> None:
    """Reset stats for a domain (e.g., after circuit breaker reset)."""
    _domain_stats[domain] = {
        "total": 0, "success": 0, "blocked": 0, "captcha": 0, "failed": 0,
        "latencies_ms": [], "last_flush": time.time(),
    }


def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * p)
    return sorted_data[min(idx, len(sorted_data) - 1)]
