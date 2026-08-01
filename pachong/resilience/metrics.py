"""Prometheus metric definitions for the pachong system.

All metrics follow Prometheus naming conventions:
  pachong_<metric>_<unit>

Exposed at /metrics for Prometheus scraping.
"""

from __future__ import annotations

from prometheus_client import REGISTRY as PROM_REGISTRY
from prometheus_client import Counter, Gauge, Histogram, Info, generate_latest

# ── Task metrics ─────────────────────────────────────────────────────────────

tasks_dispatched = Counter(
    "pachong_tasks_dispatched_total",
    "Total tasks dispatched from scheduler to Kafka",
    ["priority_bucket"],
)

tasks_processed = Counter(
    "pachong_tasks_processed_total",
    "Total tasks processed by workers",
    ["domain", "engine", "status"],
)

tasks_deferred = Counter(
    "pachong_tasks_deferred_total",
    "Tasks deferred due to rate limiting",
    ["domain"],
)

tasks_failed = Counter(
    "pachong_tasks_failed_total",
    "Total failed tasks",
    ["domain", "reason"],
)

task_latency_seconds = Histogram(
    "pachong_task_latency_seconds",
    "Task processing latency in seconds",
    ["domain", "engine"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

# ── Network metrics ──────────────────────────────────────────────────────────

http_requests_total = Counter(
    "pachong_http_requests_total",
    "Total HTTP requests made",
    ["domain", "engine", "status_code"],
)

http_request_latency_seconds = Histogram(
    "pachong_http_request_latency_seconds",
    "HTTP request latency",
    ["domain", "engine"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

engine_escalations = Counter(
    "pachong_engine_escalations_total",
    "Number of engine escalations (HTTP→Playwright etc.)",
    ["from_engine", "to_engine", "reason"],
)

# ── Anti-detection metrics ───────────────────────────────────────────────────

identity_rotations = Counter(
    "pachong_identity_rotations_total",
    "Identity rotation events",
    ["reason"],
)

proxy_health_checks = Counter(
    "pachong_proxy_health_checks_total",
    "Proxy health check results",
    ["status"],  # healthy, unhealthy, banned
)

# ── Ban detection metrics ────────────────────────────────────────────────────

ban_score = Gauge(
    "pachong_ban_score",
    "Current ban danger index for a domain (0=safe, 1=blocked)",
    ["domain"],
)

domain_block_rate = Gauge(
    "pachong_domain_block_rate",
    "Current block rate for a domain",
    ["domain"],
)

domain_qps = Gauge(
    "pachong_domain_qps",
    "Current allowed requests per second for a domain",
    ["domain"],
)

# ── Extraction metrics ───────────────────────────────────────────────────────

extractions_total = Counter(
    "pachong_extractions_total",
    "Extraction results by strategy",
    ["domain", "strategy", "status"],
)

rule_cache_hits = Counter(
    "pachong_rule_cache_hits_total",
    "Extraction rule cache hits/misses",
    ["domain", "result"],  # "hit", "miss"
)

llm_healer_calls = Counter(
    "pachong_llm_healer_calls_total",
    "LLM healer invocations",
    ["domain", "status"],  # "lock_acquired", "lock_contention", "success", "failed"
)

# ── System metrics ───────────────────────────────────────────────────────────

kafka_queue_depth = Gauge(
    "pachong_kafka_queue_depth",
    "Approximate number of pending messages in Kafka topics",
    ["topic"],
)

proxy_pool_size = Gauge(
    "pachong_proxy_pool_size",
    "Current number of active proxies",
)

active_workers = Gauge(
    "pachong_active_workers",
    "Number of active worker processes",
)

pid_controller_state = Gauge(
    "pachong_pid_controller",
    "PID controller internal state",
    ["domain", "term"],  # p_term, i_term, d_term, output
)

# ── Exposition ───────────────────────────────────────────────────────────────


def get_metrics() -> bytes:
    """Generate Prometheus text format metrics (for /metrics endpoint)."""
    return generate_latest(PROM_REGISTRY)


# ── Info ─────────────────────────────────────────────────────────────────────

# ── New business metrics ─────────────────────────────────────────────────────

extractor_field_completeness = Histogram(
    "pachong_extractor_field_completeness",
    "Distribution of extracted field counts per task",
    ["domain", "strategy"],
    buckets=[0, 1, 2, 3, 5, 8, 12, 20],
)

llm_cache_hit_ratio = Gauge(
    "pachong_llm_cache_hit_ratio",
    "LLM cache hit rate (rolling window)",
)

ban_detector_anomaly_count = Counter(
    "pachong_ban_detector_anomalies_total",
    "Number of anomaly detections by ban detector",
    ["domain"],
)

circuit_breaker_trips = Counter(
    "pachong_circuit_breaker_trips_total",
    "Number of circuit breaker openings",
    ["component", "domain"],
)

build_info = Info("pachong_build", "Pachong build information")
build_info.info({"version": "0.2.0"})
