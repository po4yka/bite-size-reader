"""Input validation functions for Firecrawl client.

This module provides validation functions for:
- Client initialization parameters
- Scrape method inputs (URL, request_id)
- Search method inputs (query, limit, request_id)
"""

from __future__ import annotations


def validate_init(
    *,
    api_key: str,
    timeout_sec: int | float,
    max_retries: int,
    backoff_base: float,
    max_connections: int,
    max_keepalive_connections: int,
    keepalive_expiry: float,
    credit_warning_threshold: int,
    credit_critical_threshold: int,
    max_response_size_mb: int,
) -> None:
    """Validate FirecrawlClient constructor parameters.

    Args:
        api_key: Firecrawl API key (must start with 'fc-')
        timeout_sec: Request timeout in seconds (1-300)
        max_retries: Maximum retry attempts (0-10)
        backoff_base: Base delay for exponential backoff (>=0)
        max_connections: Maximum HTTP connections (1-100)
        max_keepalive_connections: Maximum keepalive connections (1-50)
        keepalive_expiry: Keepalive expiry in seconds (1.0-300.0)
        credit_warning_threshold: Warning threshold for credits (1-10000)
        credit_critical_threshold: Critical threshold for credits (1-1000)
        max_response_size_mb: Maximum response size in MB (1-1024)

    Raises:
        ValueError: If any parameter is invalid
    """
    if not api_key or not isinstance(api_key, str):
        msg = "API key is required"
        raise ValueError(msg)
    if not api_key.startswith("fc-"):
        msg = "API key must start with 'fc-'"
        raise ValueError(msg)

    if not isinstance(timeout_sec, int | float) or timeout_sec <= 0 or timeout_sec > 300:
        msg = "Timeout must be positive and <=300s"
        raise ValueError(msg)

    if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 10:
        msg = "Max retries must be between 0 and 10"
        raise ValueError(msg)

    if not isinstance(backoff_base, int | float) or backoff_base < 0:
        msg = "Backoff base must be non-negative"
        raise ValueError(msg)

    if not isinstance(max_connections, int) or max_connections < 1 or max_connections > 100:
        msg = "Max connections must be between 1 and 100"
        raise ValueError(msg)

    if (
        not isinstance(max_keepalive_connections, int)
        or max_keepalive_connections < 1
        or max_keepalive_connections > 50
    ):
        msg = "Max keepalive connections must be between 1 and 50"
        raise ValueError(msg)

    if (
        not isinstance(keepalive_expiry, int | float)
        or keepalive_expiry < 1.0
        or keepalive_expiry > 300.0
    ):
        msg = "Keepalive expiry must be between 1.0 and 300.0 seconds"
        raise ValueError(msg)

    if (
        not isinstance(credit_warning_threshold, int)
        or credit_warning_threshold < 1
        or credit_warning_threshold > 10000
    ):
        msg = "Credit warning threshold must be between 1 and 10000"
        raise ValueError(msg)

    if (
        not isinstance(credit_critical_threshold, int)
        or credit_critical_threshold < 1
        or credit_critical_threshold > 1000
    ):
        msg = "Credit critical threshold must be between 1 and 1000"
        raise ValueError(msg)

    if (
        not isinstance(max_response_size_mb, int)
        or max_response_size_mb < 1
        or max_response_size_mb > 1024
    ):
        msg = "Max response size must be between 1 and 1024 MB"
        raise ValueError(msg)


def validate_scrape_inputs(url: str, request_id: int | None) -> None:
    """Validate scrape_markdown method inputs.

    Args:
        url: URL to scrape (required, max 2048 chars)
        request_id: Optional request ID (must be positive int if provided)

    Raises:
        ValueError: If any input is invalid
    """
    if not url or not isinstance(url, str):
        msg = "URL is required"
        raise ValueError(msg)

    if len(url) > 2048:
        msg = "URL too long"
        raise ValueError(msg)

    if request_id is not None and (not isinstance(request_id, int) or request_id <= 0):
        msg = "Invalid request_id"
        raise ValueError(msg)


def validate_search_inputs(query: str, limit: int, request_id: int | None) -> str:
    """Validate search method inputs and return trimmed query.

    Args:
        query: Search query (required, max 500 chars after trim)
        limit: Number of results (1-10)
        request_id: Optional request ID (must be positive int if provided)

    Returns:
        Trimmed query string

    Raises:
        ValueError: If any input is invalid
    """
    trimmed_query = str(query or "").strip()

    if not trimmed_query:
        msg = "Search query is required"
        raise ValueError(msg)

    if len(trimmed_query) > 500:
        msg = "Search query too long"
        raise ValueError(msg)

    if not isinstance(limit, int):
        msg = "Search limit must be an integer"
        raise ValueError(msg)

    if limit <= 0 or limit > 10:
        msg = "Search limit must be between 1 and 10"
        raise ValueError(msg)

    if request_id is not None and (not isinstance(request_id, int) or request_id <= 0):
        msg = "Invalid request_id"
        raise ValueError(msg)

    return trimmed_query
