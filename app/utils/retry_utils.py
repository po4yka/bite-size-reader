"""Retry utilities for handling transient errors with exponential backoff.

This module provides utilities for retrying operations that may fail due to
transient errors like network issues, rate limits, or temporary API outages.
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from app.core.backoff import sleep_backoff

logger = logging.getLogger(__name__)

T = TypeVar("T")


def is_retryable_status_code(status_code: int) -> bool:
    """Check if an HTTP status code represents a retryable error.

    Retryable codes:
    - 408: Request Timeout
    - 429: Too Many Requests
    - 5xx: Server Errors
    """
    return status_code in {408, 429} or status_code >= 500


def is_transient_error(error: Exception) -> bool:
    """Determine if an error is transient and worth retrying.

    Args:
        error: The exception to check

    Returns:
        True if the error appears to be transient, False otherwise

    Transient errors include:
    - Network-related errors (connection, timeout, DNS)
    - Rate limiting errors (429)
    - Temporary server errors (5xx)
    - Timeout errors (408)
    """
    # Check for HTTP status codes (e.g., httpx.HTTPStatusError, aiohttp.ClientResponseError)
    if hasattr(error, "response") and hasattr(error.response, "status_code"):
        try:
            status_code = int(error.response.status_code)
            if is_retryable_status_code(status_code):
                return True
            # Message is not modified (400) is NOT transient/retryable
            if status_code == 400 and "not modified" in str(error).lower():
                return False
        except (ValueError, TypeError):
            pass

    # Check for status_code attribute directly
    if hasattr(error, "status_code"):
        try:
            status_code = int(error.status_code)
            if is_retryable_status_code(status_code):
                return True
            if status_code == 400 and "not modified" in str(error).lower():
                return False
        except (ValueError, TypeError):
            pass

    error_str = str(error).lower()

    # "Message is not modified" is a common Telegram error that should NOT be retried
    if "message is not modified" in error_str or "message_not_modified" in error_str:
        return False

    # Transient error keywords
    transient_keywords = [
        "timeout",
        "connection",
        "network",
        "rate limit",
        "too many requests",
        "temporary",
        "unavailable",
        "gateway",
        "bad gateway",
        "service unavailable",
        "gateway timeout",
        "try again",
        "retry",
        "deadline exceeded",
        "flood",
        "retry after",
    ]

    # Check if error message contains transient keywords
    if any(keyword in error_str for keyword in transient_keywords):
        return True

    # Check exception types
    exception_type = type(error).__name__.lower()
    transient_types = [
        "timeout",
        "connectionerror",
        "networkerror",
        "httperror",
        "serviceunavailable",
        "gatewaytimeout",
        "deadlineexceeded",
    ]

    return any(exc_type in exception_type for exc_type in transient_types)


async def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    **kwargs: Any,
) -> tuple[Any, bool]:
    """Retry an async function with exponential backoff.

    Args:
        func: The async function to retry
        *args: Positional arguments to pass to func
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds between retries (default: 0.5)
        max_delay: Maximum delay in seconds between retries (default: 60.0)
        backoff_factor: Deprecated/Ignored. The underlying sleep_backoff uses base 2.
        **kwargs: Keyword arguments to pass to func

    Returns:
        Tuple of (result, success):
        - result: The function's return value, or None if all retries failed
        - success: True if function succeeded, False if all retries exhausted
    """
    for attempt in range(max_retries + 1):
        try:
            result = await func(*args, **kwargs)
            if attempt > 0:
                logger.info(
                    "retry_succeeded",
                    extra={
                        "function": func.__name__,
                        "attempt": attempt + 1,
                        "total_attempts": attempt + 1,
                    },
                )
            return result, True
        except Exception as e:
            if attempt >= max_retries:
                logger.warning(
                    "retry_exhausted",
                    extra={
                        "function": func.__name__,
                        "error": str(e),
                        "total_attempts": attempt + 1,
                    },
                )
                return None, False

            if not is_transient_error(e):
                logger.debug(
                    "non_transient_error_no_retry",
                    extra={
                        "function": func.__name__,
                        "error": str(e),
                        "attempt": attempt + 1,
                    },
                )
                return None, False

            logger.debug(
                "retrying_after_transient_error",
                extra={
                    "function": func.__name__,
                    "error": str(e),
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "backoff_base": initial_delay,
                },
            )

            # Use centralized backoff with jitter
            await sleep_backoff(attempt, backoff_base=initial_delay, max_delay=max_delay)

    # Should never reach here, but just in case
    return None, False


async def retry_telegram_operation(
    func: Callable[..., Any],
    *args: Any,
    operation_name: str = "telegram_operation",
    **kwargs: Any,
) -> tuple[Any, bool]:
    """Retry a Telegram API operation with sensible defaults.

    This is a convenience wrapper around retry_with_backoff with defaults
    optimized for Telegram API operations.

    Args:
        func: The async function to retry
        *args: Positional arguments to pass to func
        operation_name: Name of the operation for logging (default: "telegram_operation")
        **kwargs: Keyword arguments to pass to func

    Returns:
        Tuple of (result, success) - see retry_with_backoff for details

    Default retry parameters:
    - max_retries: 3
    - initial_delay: 0.5 seconds
    - max_delay: 5.0 seconds
    """
    logger.debug(
        "attempting_telegram_operation",
        extra={"operation": operation_name, "function": func.__name__},
    )

    result, success = await retry_with_backoff(
        func,
        *args,
        max_retries=3,
        initial_delay=0.5,
        max_delay=5.0,
        **kwargs,
    )

    if success:
        logger.debug("telegram_operation_succeeded", extra={"operation": operation_name})
    else:
        logger.warning("telegram_operation_failed", extra={"operation": operation_name})

    return result, success
