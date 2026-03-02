"""Shared message sanitization helpers for LLM request logging."""

from __future__ import annotations

from typing import Any


def sanitize_messages_for_logging(
    messages: list[dict[str, Any]], *, content_limit: int = 1000
) -> list[dict[str, Any]]:
    """Return sanitized message copies safe for logs and persistence."""
    sanitized: list[dict[str, Any]] = []
    for message in messages:
        sanitized_message = dict(message)
        content = sanitized_message.get("content", "")
        if isinstance(content, str) and len(content) > content_limit:
            sanitized_message["content"] = content[:content_limit] + "...[truncated]"
        sanitized.append(sanitized_message)
    return sanitized
