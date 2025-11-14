"""Retry utilities for handling transient errors with exponential backoff.

This module provides utilities for retrying operations that may fail due to
transient errors like network issues, rate limits, or temporary API outages.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def is_transient_error(error: Exception) -> bool:
    """Determine if an error is transient and worth retrying.

    Args:
        error: The exception to check

    Returns:
        True if the error appears to be transient, False otherwise

    Transient errors include:
    - Network-related errors (connection, timeout, DNS)
    - Rate limiting errors
    - Temporary server errors (5xx)
    - Message not modified errors (safe to ignore)
    """
    error_str = str(error).lower()

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
    ]

    # Check if error message contains transient keywords
    if any(keyword in error_str for keyword in transient_keywords):
        return True

    # "Message is not modified" is not really an error, safe to treat as transient
    if "message is not modified" in error_str:
        return True

    # Check exception types
    exception_type = type(error).__name__.lower()
    transient_types = [
        "timeout",
        "connectionerror",
        "networkerror",
        "httperror",
    ]

    return any(exc_type in exception_type for exc_type in transient_types)


async def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
    **kwargs: Any,
) -> tuple[Any, bool]:
    """Retry an async function with exponential backoff.

    Args:
        func: The async function to retry
        *args: Positional arguments to pass to func
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds between retries (default: 0.5)
        max_delay: Maximum delay in seconds between retries (default: 10.0)
        backoff_factor: Factor to multiply delay by after each retry (default: 2.0)
        **kwargs: Keyword arguments to pass to func

    Returns:
        Tuple of (result, success):
        - result: The function's return value, or None if all retries failed
        - success: True if function succeeded, False if all retries exhausted

    Example:
        >>> async def unstable_api_call(url: str) -> dict:
        ...     # May fail with transient errors
        ...     return await fetch(url)
        >>>
        >>> result, success = await retry_with_backoff(
        ...     unstable_api_call,
        ...     "https://api.example.com/data",
        ...     max_retries=3
        ... )
        >>> if success:
        ...     print(f"Got result: {result}")
        ... else:
        ...     print("Failed after all retries")
    """
    delay = initial_delay

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
            # Check if this is the last attempt
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

            # Check if error is transient
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

            # Calculate delay for next attempt
            actual_delay = min(delay, max_delay)

            logger.debug(
                "retrying_after_transient_error",
                extra={
                    "function": func.__name__,
                    "error": str(e),
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "delay_seconds": actual_delay,
                },
            )

            # Wait before retrying
            await asyncio.sleep(actual_delay)

            # Increase delay for next attempt (exponential backoff)
            delay *= backoff_factor

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
    - backoff_factor: 2.0
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
        backoff_factor=2.0,
        **kwargs,
    )

    if success:
        logger.debug("telegram_operation_succeeded", extra={"operation": operation_name})
    else:
        logger.warning("telegram_operation_failed", extra={"operation": operation_name})

    return result, success
