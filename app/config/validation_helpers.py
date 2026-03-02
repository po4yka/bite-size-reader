"""Shared validators for configuration models."""

from __future__ import annotations

from typing import Any


def parse_positive_int(value: Any, *, field_name: str, default: Any) -> int:
    """Parse a positive integer with consistent error messaging."""
    raw = value if value not in (None, "") else default
    try:
        parsed = int(str(raw))
    except ValueError as exc:
        msg = f"{field_name.replace('_', ' ')} must be a valid integer"
        raise ValueError(msg) from exc
    if parsed <= 0:
        msg = f"{field_name.replace('_', ' ').capitalize()} must be positive"
        raise ValueError(msg)
    return parsed
