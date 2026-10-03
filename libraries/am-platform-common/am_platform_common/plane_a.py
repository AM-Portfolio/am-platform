"""Plane A observability: Prometheus /metrics for AM Platform FastAPI services.

Matches ``observability.yaml`` ``metrics_application`` — every series carries
``application=`` for Technical Service discovery. Domain counters from
``signals.domain`` are registered here so they appear on scrape even at zero.
"""

from __future__ import annotations

import logging
import time
from typing import Iterable

from fastapi import FastAPI, Request, Response

logger = logging.getLogger(__name__)

_EXCLUDED_PATHS = {
    "/metrics",
    "/health",
    "/ready",
    "/live",
    "/health/live",
    "/health/ready",
}

# Module-level handles for domain counters (set by setup_plane_a).
_DOMAIN: dict[str, object] = {}


def domain_counter(name: str):
    """Return a registered domain Counter, or None if plane_a not set up."""
    return _DOMAIN.get(name)


def setup_plane_a(
    app: FastAPI,
    *,
    application: str,
    domain: Iterable[str] | None = None,
) -> None:
    """Expose /metrics + HTTP RED metrics; optionally register domain counters."""
    try:
        from prometheus_client import (
            CONTENT_TYPE_LATEST,
            Counter,
            Gauge,
            Histogram,
            generate_latest,
        )
    except ImportError:
        logger.warning("prometheus_client missing — /metrics not enabled")
        return

    up = Gauge("am_process_up", "1 if the process is up", ["application"])
    up.labels(application=application).set(1)

    requests_total = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["application", "method", "handler", "status"],
    )
    request_duration = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["application", "method", "handler"],
    )

    for name in domain or ():
        metric_name = name if name.endswith("_total") else f"{name}_total"
        help_text = metric_name.replace("_", " ")
        counter = Counter(metric_name, help_text, ["application"])
        # Register zero series so scrape shows the metric before first event.
        counter.labels(application=application)
        _DOMAIN[metric_name] = counter
        _DOMAIN[name] = counter

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        path = request.url.path
        if path in _EXCLUDED_PATHS or path.endswith("/metrics"):
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        handler = path if len(path) < 120 else path[:117] + "..."
        requests_total.labels(
            application, request.method, handler, str(response.status_code)
        ).inc()
        request_duration.labels(application, request.method, handler).observe(elapsed)
        return response

    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    logger.info(
        "Prometheus /metrics enabled application=%s domain=%s",
        application,
        list(domain or ()),
    )


def inc_domain(name: str, application: str, amount: float = 1.0) -> None:
    """Increment a domain counter if registered."""
    counter = _DOMAIN.get(name)
    if counter is None:
        return
    try:
        counter.labels(application=application).inc(amount)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — metrics must not break requests
        logger.exception("failed to inc domain metric %s", name)
