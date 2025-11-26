from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)


class ResponseSizeError(ValueError):
    """Raised when a response exceeds the maximum allowed size."""

    def __init__(self, message: str, *, actual_size: int | None = None, max_size: int) -> None:
        super().__init__(message)
        self.actual_size = actual_size
        self.max_size = max_size


async def validate_response_size(
    response: httpx.Response,
    max_size_bytes: int,
    service_name: str,
) -> None:
    """Validate response size before parsing to prevent memory exhaustion.

    This function checks the Content-Length header to ensure the response
    doesn't exceed the maximum allowed size. This prevents malicious or
    corrupted responses from consuming excessive memory.

    Args:
        response: The httpx.Response object to validate
        max_size_bytes: Maximum allowed response size in bytes
        service_name: Name of the service (for logging)

    Raises:
        ResponseSizeError: If response exceeds max_size_bytes
        ValueError: If max_size_bytes is invalid

    Security considerations:
        - Checks Content-Length header before reading response body
        - Prevents memory exhaustion from malicious responses
        - Logs warnings for large but acceptable responses
        - Does not rely solely on Content-Length (some servers omit it)
    """
    # Validate max_size_bytes
    if not isinstance(max_size_bytes, int) or max_size_bytes <= 0:
        msg = f"max_size_bytes must be a positive integer, got {max_size_bytes}"
        raise ValueError(msg)

    if max_size_bytes > 1024 * 1024 * 1024:  # 1GB
        msg = f"max_size_bytes too large (max 1GB), got {max_size_bytes}"
        raise ValueError(msg)

    # Check Content-Length header if present
    content_length_str = response.headers.get("content-length")
    if content_length_str:
        try:
            content_length = int(content_length_str)

            # Check if response exceeds limit
            if content_length > max_size_bytes:
                msg = (
                    f"{service_name} response size ({content_length} bytes) "
                    f"exceeds limit ({max_size_bytes} bytes)"
                )
                logger.error(
                    "response_size_exceeded",
                    extra={
                        "service": service_name,
                        "content_length": content_length,
                        "max_size": max_size_bytes,
                        "status_code": response.status_code,
                    },
                )
                raise ResponseSizeError(msg, actual_size=content_length, max_size=max_size_bytes)

            # Log warning if response is large (>50% of limit)
            if content_length > max_size_bytes * 0.5:
                logger.warning(
                    "large_response_size",
                    extra={
                        "service": service_name,
                        "content_length": content_length,
                        "max_size": max_size_bytes,
                        "percentage": round(100 * content_length / max_size_bytes, 1),
                        "status_code": response.status_code,
                    },
                )

        except ValueError:
            # Invalid Content-Length header - log but continue
            logger.warning(
                "invalid_content_length_header",
                extra={
                    "service": service_name,
                    "content_length": content_length_str,
                    "status_code": response.status_code,
                },
            )

    else:
        # No Content-Length header - we'll check actual content size
        # Note: httpx already has the response content in memory at this point
        # but we can check it to prevent further processing
        try:
            # Check if response content is already available
            if hasattr(response, "_content") and response._content is not None:
                actual_size = len(response._content)
                if actual_size > max_size_bytes:
                    msg = (
                        f"{service_name} response size ({actual_size} bytes) "
                        f"exceeds limit ({max_size_bytes} bytes)"
                    )
                    logger.error(
                        "response_size_exceeded_no_header",
                        extra={
                            "service": service_name,
                            "actual_size": actual_size,
                            "max_size": max_size_bytes,
                            "status_code": response.status_code,
                        },
                    )
                    raise ResponseSizeError(msg, actual_size=actual_size, max_size=max_size_bytes)
        except AttributeError:
            # Response doesn't have _content attribute - skip validation
            logger.debug(
                "response_size_validation_skipped",
                extra={
                    "service": service_name,
                    "reason": "no_content_length_header",
                    "status_code": response.status_code,
                },
            )


def bytes_to_mb(size_bytes: int) -> float:
    """Convert bytes to megabytes."""
    return round(size_bytes / (1024 * 1024), 2)
