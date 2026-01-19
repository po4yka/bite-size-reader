"""Custom exceptions for Firecrawl client operations.

This module defines a hierarchy of exceptions for handling various
error conditions in the Firecrawl adapter:

- FirecrawlError: Base exception with context support
- ConfigurationError: Invalid client configuration
- ValidationError: Invalid input parameters
- APIError: General API error responses
- RateLimitError: 429 rate limit exceeded
- NetworkError: Connection/timeout errors
- ContentError: No content returned
"""

from __future__ import annotations

from typing import Any


class FirecrawlError(Exception):
    """Base exception for Firecrawl client errors.

    Provides context storage for debugging and logging.
    """

    def __init__(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self) -> str:
        if self.context:
            return f"{self.message} (context: {self.context})"
        return self.message


class ConfigurationError(FirecrawlError):
    """Raised when client configuration is invalid.

    Examples:
    - Missing or invalid API key
    - Invalid timeout values
    - Invalid connection pool settings
    """

    def __init__(
        self,
        message: str,
        *,
        parameter: str | None = None,
        value: Any = None,
    ) -> None:
        context = {}
        if parameter:
            context["parameter"] = parameter
        if value is not None:
            context["value"] = value
        super().__init__(message, context=context)
        self.parameter = parameter
        self.value = value


class ValidationError(FirecrawlError):
    """Raised when input parameters are invalid.

    Examples:
    - Empty or missing URL
    - URL too long
    - Invalid search query
    - Invalid request_id
    """

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        value: Any = None,
    ) -> None:
        context = {}
        if field:
            context["field"] = field
        if value is not None:
            context["value"] = str(value)[:100]
        super().__init__(message, context=context)
        self.field = field
        self.value = value


class APIError(FirecrawlError):
    """Raised when Firecrawl API returns an error response.

    Stores HTTP status code and API-provided error details.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        response_data: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        context: dict[str, Any] = {}
        if status_code is not None:
            context["status_code"] = status_code
        if error_code:
            context["error_code"] = error_code
        if correlation_id:
            context["correlation_id"] = correlation_id
        super().__init__(message, context=context)
        self.status_code = status_code
        self.error_code = error_code
        self.response_data = response_data
        self.correlation_id = correlation_id


class RateLimitError(APIError):
    """Raised when rate limit (HTTP 429) is exceeded.

    Provides retry_after hint if available from response headers.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        retry_after: int | None = None,
        correlation_id: str | None = None,
    ) -> None:
        context: dict[str, Any] = {"status_code": 429}
        if retry_after is not None:
            context["retry_after"] = retry_after
        super().__init__(
            message,
            status_code=429,
            correlation_id=correlation_id,
        )
        self.retry_after = retry_after
        self.context.update(context)


class NetworkError(FirecrawlError):
    """Raised for connection, timeout, or transport errors.

    Wraps underlying HTTP client exceptions.
    """

    def __init__(
        self,
        message: str,
        *,
        original_error: Exception | None = None,
        url: str | None = None,
    ) -> None:
        context = {}
        if url:
            context["url"] = url
        if original_error:
            context["original_error"] = type(original_error).__name__
        super().__init__(message, context=context)
        self.original_error = original_error
        self.url = url


class ContentError(FirecrawlError):
    """Raised when no usable content is returned.

    Examples:
    - Empty markdown and HTML
    - All data items have errors
    - success=false without content
    """

    def __init__(
        self,
        message: str = "No content returned",
        *,
        url: str | None = None,
        correlation_id: str | None = None,
        has_markdown: bool = False,
        has_html: bool = False,
    ) -> None:
        context: dict[str, Any] = {
            "has_markdown": has_markdown,
            "has_html": has_html,
        }
        if url:
            context["url"] = url
        if correlation_id:
            context["correlation_id"] = correlation_id
        super().__init__(message, context=context)
        self.url = url
        self.correlation_id = correlation_id
        self.has_markdown = has_markdown
        self.has_html = has_html


class ResponseSizeExceededError(FirecrawlError):
    """Raised when response exceeds maximum allowed size.

    This is a wrapper for the core ResponseSizeError for
    Firecrawl-specific handling.
    """

    def __init__(
        self,
        message: str,
        *,
        actual_size: int | None = None,
        max_size: int | None = None,
        url: str | None = None,
    ) -> None:
        context: dict[str, Any] = {}
        if actual_size is not None:
            context["actual_size_bytes"] = actual_size
        if max_size is not None:
            context["max_size_bytes"] = max_size
        if url:
            context["url"] = url
        super().__init__(message, context=context)
        self.actual_size = actual_size
        self.max_size = max_size
        self.url = url
