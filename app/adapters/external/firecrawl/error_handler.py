"""Error handling and retry logic for Firecrawl client.

This module provides:
- Retry decision logic
- Exponential backoff with jitter
- HTTP status error mapping
- Search error result builders
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Any

from app.adapters.external.firecrawl.models import FirecrawlSearchResult

if TYPE_CHECKING:
    import json

    import httpx

    from app.adapters.external.firecrawl.payload_logger import PayloadLogger
    from app.core.http_utils import ResponseSizeError


class ErrorHandler:
    """Handles errors, retries, and fallback logic for Firecrawl API calls."""

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        max_response_size_bytes: int = 50 * 1024 * 1024,
        payload_logger: PayloadLogger | None = None,
    ) -> None:
        """Initialize ErrorHandler.

        Args:
            max_retries: Maximum number of retry attempts
            backoff_base: Base delay for exponential backoff
            max_response_size_bytes: Maximum allowed response size
            payload_logger: Optional payload logger instance
        """
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._max_response_size_bytes = max_response_size_bytes
        self._payload_logger = payload_logger
        self._logger = logging.getLogger(__name__)

    async def sleep_backoff(self, attempt: int) -> None:
        """Sleep with exponential backoff and jitter.

        Args:
            attempt: Current attempt number (0-indexed)
        """
        base_delay = max(0.0, self._backoff_base * (2**attempt))
        jitter = 1.0 + random.uniform(-0.25, 0.25)
        await asyncio.sleep(base_delay * jitter)

    def should_retry(self, status_code: int, attempt: int, error_text: str | None = None) -> bool:
        """Determine if a request should be retried based on status code and error text.

        Args:
            status_code: HTTP status code from response
            attempt: Current attempt number
            error_text: Optional error message text to check for timeout indicators

        Returns:
            True if request should be retried
        """
        if attempt >= self._max_retries:
            return False
        # Retry on rate limit or server errors
        if status_code == 429 or status_code >= 500:
            return True
        # Retry on timeout errors (HTTP 408 Request Timeout)
        if status_code == 408:
            return True
        # Retry if error text indicates a timeout
        if error_text:
            error_lower = error_text.lower()
            if "timeout" in error_lower or "timed out" in error_lower:
                return True
        return False

    def handle_retryable_errors(
        self,
        *,
        resp: httpx.Response,
        data: dict[str, Any],
        attempt: int,
        cur_mobile: bool,
        cur_pdf: bool,
        pdf_hint: bool,
    ) -> tuple[float | None, bool]:
        """Handle retryable HTTP errors and determine retry strategy.

        Args:
            resp: HTTP response object
            data: Parsed response data
            attempt: Current attempt number
            cur_mobile: Current mobile mode setting
            cur_pdf: Current PDF mode setting
            pdf_hint: Whether URL hints at PDF content

        Returns:
            Tuple of (retry_delay, should_toggle_mobile):
            - retry_delay: Delay before retry in seconds, or None if not retryable
            - should_toggle_mobile: Whether to toggle mobile/pdf modes on retry
        """
        error_text = data.get("error") or data.get("message") or ""

        if resp.status_code == 429:
            retry_after = data.get("retry_after", 60)
            if attempt < self._max_retries:
                if self._payload_logger:
                    self._payload_logger.log_rate_limit(
                        status=resp.status_code,
                        retry_after=retry_after,
                        attempt=attempt,
                    )
                delay = min(retry_after, self._backoff_base * (2**attempt))
                return delay, False
            return None, False

        if resp.status_code >= 500:
            if attempt < self._max_retries:
                delay = self._backoff_base * (2**attempt)
                return delay, True

        # Handle timeout errors (HTTP 408 or timeout/timed out in error message)
        error_lower = str(error_text).lower() if error_text else ""
        is_timeout_error = "timeout" in error_lower or "timed out" in error_lower
        if resp.status_code == 408 or is_timeout_error:
            if attempt < self._max_retries:
                delay = self._backoff_base * (2**attempt)
                self._logger.warning(
                    "firecrawl_timeout_retry",
                    extra={
                        "status_code": resp.status_code,
                        "attempt": attempt,
                        "error_text": str(error_text)[:200],
                    },
                )
                return delay, False  # Don't toggle mobile on timeout, just retry
            return None, False

        return None, False

    @staticmethod
    def map_status_error(status_code: int, error_message: str) -> str:
        """Map HTTP status codes to human-readable error messages.

        Args:
            status_code: HTTP status code
            error_message: Original error message from API

        Returns:
            Human-readable error message with status prefix
        """
        if status_code == 400:
            return f"Bad Request: {error_message}"
        if status_code == 401:
            return f"Unauthorized: {error_message}"
        if status_code == 402:
            return f"Payment Required: {error_message}"
        if status_code == 404:
            return f"Not Found: {error_message}"
        if status_code == 429:
            return f"Rate Limit Exceeded: {error_message}"
        if status_code >= 500:
            return f"Server Error: {error_message}"
        return error_message

    def build_search_size_error(
        self,
        exc: ResponseSizeError,
        query: str,
        started: float,
    ) -> FirecrawlSearchResult:
        """Build search result for response size exceeded error.

        Args:
            exc: ResponseSizeError exception
            query: Search query
            started: Request start time (perf_counter)

        Returns:
            FirecrawlSearchResult with error status
        """
        latency = int((time.perf_counter() - started) * 1000)
        error_text = str(exc)

        self._logger.error(
            "firecrawl_search_response_too_large",
            extra={
                "error": error_text,
                "query": query,
                "max_size_mb": self._max_response_size_bytes / (1024 * 1024),
            },
        )

        if self._payload_logger:
            self._payload_logger.log_search_size_error(error_text, query)

        return FirecrawlSearchResult(
            status="error",
            results=[],
            latency_ms=latency,
            error_text=f"Response too large: {error_text}",
            http_status=None,
        )

    def build_search_http_error(
        self,
        exc: Exception,
        query: str,
        started: float,
    ) -> FirecrawlSearchResult:
        """Build search result for HTTP transport error.

        Args:
            exc: HTTP exception
            query: Search query
            started: Request start time (perf_counter)

        Returns:
            FirecrawlSearchResult with error status
        """
        latency = int((time.perf_counter() - started) * 1000)
        error_text = str(exc)

        self._logger.exception(
            "firecrawl_search_http_error",
            extra={"error": error_text, "query": query},
        )

        if self._payload_logger:
            self._payload_logger.log_search_http_error(error_text, query)

        return FirecrawlSearchResult(
            status="error",
            results=[],
            latency_ms=latency,
            error_text=error_text,
            http_status=None,
        )

    def build_search_invalid_json_error(
        self,
        exc: json.JSONDecodeError,
        resp: httpx.Response,
        latency: int,
    ) -> FirecrawlSearchResult:
        """Build search result for invalid JSON response.

        Args:
            exc: JSONDecodeError exception
            resp: HTTP response object
            latency: Response latency in milliseconds

        Returns:
            FirecrawlSearchResult with error status
        """
        error_text = f"invalid_json: {exc}"

        self._logger.exception(
            "firecrawl_search_invalid_json",
            extra={"error": error_text, "status": resp.status_code},
        )

        if self._payload_logger:
            self._payload_logger.log_search_invalid_json(resp.status_code, error_text)

        return FirecrawlSearchResult(
            status="error",
            results=[],
            latency_ms=latency,
            error_text=error_text,
            http_status=resp.status_code,
        )


async def asyncio_sleep_backoff(base: float, attempt: int) -> None:
    """Sleep with exponential backoff and jitter.

    This is a standalone function for backward compatibility.

    Args:
        base: Base delay in seconds
        attempt: Current attempt number (0-indexed)
    """
    base_delay = max(0.0, base * (2**attempt))
    jitter = 1.0 + random.uniform(-0.25, 0.25)
    await asyncio.sleep(base_delay * jitter)
