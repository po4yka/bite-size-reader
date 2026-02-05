"""Datetime coercion helpers used during sync."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def _ensure_datetime(value: Any) -> datetime | None:
    """Convert a value to datetime if it's a string, or return as-is if already datetime.

    SQLite may return datetime columns as strings depending on how they were inserted.
    Always returns timezone-aware (UTC) datetimes -- naive values are assumed UTC.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if isinstance(value, str):
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            logger.warning("ensure_datetime_parse_failed", extra={"value": repr(value)})
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
    logger.warning(
        "ensure_datetime_unexpected_type",
        extra={"type": type(value).__name__, "value": repr(value)},
    )
    return None
