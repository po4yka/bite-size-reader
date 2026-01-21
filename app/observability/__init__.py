"""Observability module for metrics, tracing, and monitoring."""

from app.observability.metrics import (
    CIRCUIT_BREAKER_STATE,
    DB_QUERY_LATENCY,
    FIRECRAWL_REQUESTS,
    OPENROUTER_COST_USD,
    OPENROUTER_TOKENS,
    REQUEST_LATENCY,
    REQUESTS_TOTAL,
    get_metrics,
    record_circuit_breaker_state,
    record_db_query,
    record_firecrawl_request,
    record_openrouter_call,
    record_request,
)

__all__ = [
    "CIRCUIT_BREAKER_STATE",
    "DB_QUERY_LATENCY",
    "FIRECRAWL_REQUESTS",
    "OPENROUTER_COST_USD",
    "OPENROUTER_TOKENS",
    "REQUESTS_TOTAL",
    "REQUEST_LATENCY",
    "get_metrics",
    "record_circuit_breaker_state",
    "record_db_query",
    "record_firecrawl_request",
    "record_openrouter_call",
    "record_request",
]
