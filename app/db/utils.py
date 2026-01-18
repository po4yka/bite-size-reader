"""Database utilities and helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


def normalize_json_container(value: Any) -> Any:
    """Normalize a container (dict/list) to standard types for JSON serialization."""
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return list(value)
    return value


def prepare_json_payload(value: Any, *, default: Any | None = None) -> Any | None:
    """Prepare a value for storage as a JSON field.

    Handles bytes decoding, string parsing, and normalization.
    """
    if value is None:
        value = default
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes | bytearray):
        try:
            value = value.decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return stripped

    normalized = normalize_json_container(value)
    try:
        json.dumps(normalized)
        return normalized
    except (TypeError, ValueError):
        try:
            coerced = json.loads(json.dumps(normalized, default=str))
        except (TypeError, ValueError):
            return None
        return coerced
