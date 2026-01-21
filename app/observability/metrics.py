"""Prometheus metrics for Bite-Size Reader.

This module provides metrics collection for monitoring the application's:
- Request throughput and latency
- Firecrawl API usage
- OpenRouter API usage and costs
- Circuit breaker states
- Database query performance

Usage:
    from app.observability.metrics import record_request, record_firecrawl_request

    # Record a request
    record_request(request_type="url", status="success", source="telegram")

    # Record Firecrawl API call
    record_firecrawl_request(status="success", endpoint="scrape", latency_ms=1500)
"""

from __future__ import annotations

import logging

# Try to import prometheus_client, but make it optional
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


logger = logging.getLogger(__name__)

# Create a custom registry to avoid conflicts with default registry
if PROMETHEUS_AVAILABLE:
    REGISTRY = CollectorRegistry()

    # Request metrics
    REQUESTS_TOTAL = Counter(
        "bsr_requests_total",
        "Total number of requests processed",
        ["type", "status", "source"],
        registry=REGISTRY,
    )

    REQUEST_LATENCY = Histogram(
        "bsr_request_latency_seconds",
        "Request latency in seconds",
        ["type", "stage"],
        buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
        registry=REGISTRY,
    )

    # Firecrawl metrics
    FIRECRAWL_REQUESTS = Counter(
        "bsr_firecrawl_requests_total",
        "Total Firecrawl API requests",
        ["status", "endpoint"],
        registry=REGISTRY,
    )

    FIRECRAWL_LATENCY = Histogram(
        "bsr_firecrawl_latency_seconds",
        "Firecrawl API latency in seconds",
        ["endpoint"],
        buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
        registry=REGISTRY,
    )

    # OpenRouter metrics
    OPENROUTER_TOKENS = Counter(
        "bsr_openrouter_tokens_total",
        "Total tokens used in OpenRouter API calls",
        ["model", "type"],
        registry=REGISTRY,
    )

    OPENROUTER_COST_USD = Counter(
        "bsr_openrouter_cost_usd_total",
        "Total cost in USD for OpenRouter API calls",
        registry=REGISTRY,
    )

    OPENROUTER_LATENCY = Histogram(
        "bsr_openrouter_latency_seconds",
        "OpenRouter API latency in seconds",
        ["model"],
        buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
        registry=REGISTRY,
    )

    # Circuit breaker metrics
    CIRCUIT_BREAKER_STATE = Gauge(
        "bsr_circuit_breaker_state",
        "Circuit breaker state (0=closed, 1=half_open, 2=open)",
        ["service"],
        registry=REGISTRY,
    )

    # Database metrics
    DB_QUERY_LATENCY = Histogram(
        "bsr_db_query_latency_seconds",
        "Database query latency in seconds",
        ["operation"],
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
        registry=REGISTRY,
    )

    DB_CONNECTIONS = Gauge(
        "bsr_db_connections_active",
        "Number of active database connections",
        registry=REGISTRY,
    )

else:
    # Create dummy metrics when prometheus_client is not available
    REGISTRY = None
    REQUESTS_TOTAL = None
    REQUEST_LATENCY = None
    FIRECRAWL_REQUESTS = None
    FIRECRAWL_LATENCY = None
    OPENROUTER_TOKENS = None
    OPENROUTER_COST_USD = None
    OPENROUTER_LATENCY = None
    CIRCUIT_BREAKER_STATE = None
    DB_QUERY_LATENCY = None
    DB_CONNECTIONS = None


def get_metrics() -> bytes:
    """Generate Prometheus metrics in text format.

    Returns:
        Prometheus metrics as bytes in text format, or empty bytes if unavailable.
    """
    if not PROMETHEUS_AVAILABLE or REGISTRY is None:
        return b"# Prometheus metrics not available (prometheus_client not installed)\n"
    return generate_latest(REGISTRY)


def get_metrics_content_type() -> str:
    """Get the content type for Prometheus metrics response."""
    if PROMETHEUS_AVAILABLE:
        return CONTENT_TYPE_LATEST
    return "text/plain; charset=utf-8"


def record_request(
    request_type: str,
    status: str,
    source: str,
    latency_seconds: float | None = None,
    stage: str = "total",
) -> None:
    """Record a request metric.

    Args:
        request_type: Type of request (url, forward, command)
        status: Request status (success, error, timeout)
        source: Request source (telegram, api, cli)
        latency_seconds: Optional latency in seconds
        stage: Processing stage (extraction, summarization, total)
    """
    if not PROMETHEUS_AVAILABLE:
        return

    REQUESTS_TOTAL.labels(type=request_type, status=status, source=source).inc()

    if latency_seconds is not None:
        REQUEST_LATENCY.labels(type=request_type, stage=stage).observe(latency_seconds)


def record_firecrawl_request(
    status: str,
    endpoint: str = "scrape",
    latency_seconds: float | None = None,
) -> None:
    """Record a Firecrawl API request metric.

    Args:
        status: Request status (success, error, timeout)
        endpoint: API endpoint (scrape, search, crawl)
        latency_seconds: Optional latency in seconds
    """
    if not PROMETHEUS_AVAILABLE:
        return

    FIRECRAWL_REQUESTS.labels(status=status, endpoint=endpoint).inc()

    if latency_seconds is not None:
        FIRECRAWL_LATENCY.labels(endpoint=endpoint).observe(latency_seconds)


def record_openrouter_call(
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float = 0.0,
    latency_seconds: float | None = None,
) -> None:
    """Record an OpenRouter API call metric.

    Args:
        model: Model name used for the call
        prompt_tokens: Number of prompt tokens used
        completion_tokens: Number of completion tokens used
        cost_usd: Cost of the call in USD
        latency_seconds: Optional latency in seconds
    """
    if not PROMETHEUS_AVAILABLE:
        return

    if prompt_tokens > 0:
        OPENROUTER_TOKENS.labels(model=model, type="prompt").inc(prompt_tokens)

    if completion_tokens > 0:
        OPENROUTER_TOKENS.labels(model=model, type="completion").inc(completion_tokens)

    if cost_usd > 0:
        OPENROUTER_COST_USD.inc(cost_usd)

    if latency_seconds is not None:
        OPENROUTER_LATENCY.labels(model=model).observe(latency_seconds)


def record_circuit_breaker_state(service: str, state: str) -> None:
    """Record circuit breaker state.

    Args:
        service: Service name (firecrawl, openrouter)
        state: Circuit breaker state (closed, half_open, open)
    """
    if not PROMETHEUS_AVAILABLE:
        return

    state_value = {"closed": 0, "half_open": 1, "open": 2}.get(state, -1)
    CIRCUIT_BREAKER_STATE.labels(service=service).set(state_value)


def record_db_query(operation: str, latency_seconds: float) -> None:
    """Record a database query metric.

    Args:
        operation: Query operation type (select, insert, update, delete)
        latency_seconds: Query latency in seconds
    """
    if not PROMETHEUS_AVAILABLE:
        return

    DB_QUERY_LATENCY.labels(operation=operation).observe(latency_seconds)


def set_db_connections(count: int) -> None:
    """Set the number of active database connections.

    Args:
        count: Number of active connections
    """
    if not PROMETHEUS_AVAILABLE:
        return

    DB_CONNECTIONS.set(count)
