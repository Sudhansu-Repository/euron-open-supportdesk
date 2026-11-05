"""Prometheus metrics for the API and the worker."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

ai_decisions = Counter(
    "supportdesk_ai_decisions_total", "AI turns by outcome and answer method", ["action", "method"]
)
jobs_processed = Counter(
    "supportdesk_jobs_total", "Background jobs by kind and result", ["kind", "result"]
)
job_seconds = Histogram(
    "supportdesk_job_seconds",
    "Background job duration",
    ["kind"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120),
)
websockets = Gauge("supportdesk_websockets", "Open WebSocket connections", ["kind"])
DEPENDENCY_ERRORS = Counter(
    "supportdesk_dependency_errors_total",
    "Failed calls to a dependency",
    ["dependency", "operation"],
)
