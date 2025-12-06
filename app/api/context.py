"""Shared API request context."""

from contextvars import ContextVar

# Correlation ID captured by middleware for use in helpers and handlers.
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)
