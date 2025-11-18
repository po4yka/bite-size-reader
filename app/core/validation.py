"""Input validation utilities for safe type conversion and validation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

T = TypeVar("T")


def safe_cast(
    value: Any,
    target_type: type[T],
    validator: Callable[[T], bool] | None = None,
    default: T | None = None,
    field_name: str = "value",
) -> T | None:
    """Safely cast and validate a value with proper error handling.

    Args:
        value: The value to cast
        target_type: The target type to cast to
        validator: Optional validation function
        default: Default value if cast/validation fails
        field_name: Name of field for logging

    Returns:
        Casted and validated value, or default if invalid

    """
    try:
        if value is None:
            return default

        casted = target_type(value)  # type: ignore[call-arg]

        if validator and not validator(casted):
            logger.warning(
                "validation_failed",
                extra={
                    "field": field_name,
                    "value_type": type(value).__name__,
                    "target_type": target_type.__name__,
                },
            )
            return default

        return casted

    except (ValueError, TypeError, OverflowError) as e:
        logger.warning(
            "cast_failed",
            extra={
                "field": field_name,
                "value_type": type(value).__name__,
                "target_type": target_type.__name__,
                "error": str(e),
            },
        )
        return default


def safe_telegram_user_id(raw_value: Any, field_name: str = "user_id") -> int | None:
    """Safely validate and convert Telegram user ID.

    Telegram user IDs are positive 32-bit integers.

    Args:
        raw_value: Raw value to validate
        field_name: Field name for logging

    Returns:
        Valid user ID or None

    """
    return safe_cast(
        raw_value,
        int,
        validator=lambda x: 0 < x < 2**31,
        default=None,
        field_name=field_name,
    )


def safe_telegram_chat_id(raw_value: Any, field_name: str = "chat_id") -> int | None:
    """Safely validate and convert Telegram chat ID.

    Telegram chat IDs can be negative for groups/channels.

    Args:
        raw_value: Raw value to validate
        field_name: Field name for logging

    Returns:
        Valid chat ID or None

    """
    return safe_cast(
        raw_value,
        int,
        validator=lambda x: -(2**31) < x < 2**31,
        default=None,
        field_name=field_name,
    )


def safe_message_id(raw_value: Any, field_name: str = "message_id") -> int | None:
    """Safely validate and convert Telegram message ID.

    Args:
        raw_value: Raw value to validate
        field_name: Field name for logging

    Returns:
        Valid message ID or None

    """
    return safe_cast(
        raw_value,
        int,
        validator=lambda x: 0 < x < 2**63,
        default=None,
        field_name=field_name,
    )


def safe_positive_int(
    raw_value: Any, max_value: int | None = None, field_name: str = "value"
) -> int | None:
    """Safely validate and convert to positive integer.

    Args:
        raw_value: Raw value to validate
        max_value: Optional maximum value
        field_name: Field name for logging

    Returns:
        Valid positive integer or None

    """

    def validator(x: int) -> bool:
        if max_value is not None:
            return 0 < x <= max_value
        return x > 0

    return safe_cast(
        raw_value,
        int,
        validator=validator,
        default=None,
        field_name=field_name,
    )


def safe_string(
    raw_value: Any,
    max_length: int | None = None,
    min_length: int = 0,
    field_name: str = "value",
) -> str | None:
    """Safely validate and convert to string.

    Args:
        raw_value: Raw value to validate
        max_length: Optional maximum length
        min_length: Minimum length (default: 0)
        field_name: Field name for logging

    Returns:
        Valid string or None

    """
    if not isinstance(raw_value, str):
        if raw_value is None:
            return None
        raw_value = str(raw_value)

    def validator(x: str) -> bool:
        return len(x) >= min_length and (max_length is None or len(x) <= max_length)

    return safe_cast(
        raw_value,
        str,
        validator=validator,
        default=None,
        field_name=field_name,
    )
