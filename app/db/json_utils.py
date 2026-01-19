"""Consolidated JSON utilities for database operations.

This module provides utilities for:
- Decoding JSON fields from database with security validation
- Normalizing legacy JSON values during migrations
- Preparing JSON payloads for storage

All JSON operations use the validators from app.core.json_depth_validator
for consistent security constraints.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.core.json_depth_validator import safe_json_parse, validate_json_structure

# Default validation limits (can be overridden per-call)
DEFAULT_JSON_MAX_SIZE = 10_000_000  # 10MB
DEFAULT_JSON_MAX_DEPTH = 20
DEFAULT_JSON_MAX_ARRAY_LENGTH = 10_000
DEFAULT_JSON_MAX_DICT_KEYS = 1_000


def decode_json_field(
    value: Any,
    *,
    max_size: int = DEFAULT_JSON_MAX_SIZE,
    max_depth: int = DEFAULT_JSON_MAX_DEPTH,
    max_array_length: int = DEFAULT_JSON_MAX_ARRAY_LENGTH,
    max_dict_keys: int = DEFAULT_JSON_MAX_DICT_KEYS,
) -> tuple[Any | None, str | None]:
    """Decode JSON field with security validation.

    Handles various input types (bytes, memoryview, str, dict, list) and
    validates the resulting structure against security constraints.

    Args:
        value: The value to decode (string, bytes, dict, list, etc.)
        max_size: Maximum size for string input
        max_depth: Maximum nesting depth
        max_array_length: Maximum array length
        max_dict_keys: Maximum dictionary keys

    Returns:
        Tuple of (decoded_value, error_message). If successful, error_message is None.

    Examples:
        >>> decode_json_field('{"key": "value"}')
        ({'key': 'value'}, None)

        >>> decode_json_field(None)
        (None, None)

        >>> decode_json_field('invalid json')
        (None, 'Invalid JSON: ...')
    """
    if value is None:
        return None, None

    # Handle memoryview
    if isinstance(value, memoryview):
        value = value.tobytes()

    # Handle bytes
    if isinstance(value, bytes | bytearray):
        try:
            value = value.decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            return None, "decode_error"

    # If already a dict/list, validate structure
    if isinstance(value, dict | list):
        valid, error = validate_json_structure(
            value,
            max_depth=max_depth,
            max_array_length=max_array_length,
            max_dict_keys=max_dict_keys,
        )
        if not valid:
            return None, error
        return value, None

    # Handle string input
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None, None

        # Use safe_json_parse with validation
        parsed, error = safe_json_parse(
            stripped,
            max_size=max_size,
            max_depth=max_depth,
            max_array_length=max_array_length,
            max_dict_keys=max_dict_keys,
        )
        if error:
            return None, error
        return parsed, None

    # For other types, check if JSON-serializable
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return None, "unsupported_type"

    # If it's a valid JSON-serializable value, return it
    return value, None


def normalize_legacy_json_value(value: Any) -> tuple[Any | None, bool, str | None]:
    """Normalize legacy JSON values during migrations.

    Handles malformed or invalid JSON data that may exist in older database
    rows by wrapping invalid text in a special structure.

    Args:
        value: The raw value from the database

    Returns:
        Tuple of (normalized_value, should_update, reason).
        - normalized_value: The processed value
        - should_update: Whether the database row should be updated
        - reason: Explanation if normalization was needed ("blank", "invalid_json")

    Examples:
        >>> normalize_legacy_json_value(None)
        (None, False, None)

        >>> normalize_legacy_json_value({"key": "value"})
        ({'key': 'value'}, False, None)

        >>> normalize_legacy_json_value("not json")
        ({'__legacy_text__': 'not json'}, True, 'invalid_json')

        >>> normalize_legacy_json_value("  ")
        (None, True, 'blank')
    """
    if value is None:
        return None, False, None

    # Handle memoryview
    if isinstance(value, memoryview):
        value = value.tobytes()

    # Handle bytes
    if isinstance(value, bytes | bytearray):
        try:
            value = value.decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            value = value.decode("utf-8", errors="replace")

    # Already valid dict/list - no normalization needed
    if isinstance(value, dict | list):
        return value, False, None

    # Handle string values
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None, True, "blank"
        try:
            json.loads(stripped)
        except json.JSONDecodeError:
            # Wrap invalid JSON text in a special structure
            return {"__legacy_text__": stripped}, True, "invalid_json"
        # Valid JSON string - no update needed (will be parsed on read)
        return None, False, None

    # Other types - try to serialize
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return {"__legacy_text__": str(value)}, True, "invalid_json"

    return value, False, None


def normalize_json_container(value: Any) -> Any:
    """Normalize a container (dict/list) to standard types for JSON serialization.

    Converts Mapping subclasses to dict and Sequence subclasses to list.

    Args:
        value: The container to normalize

    Returns:
        Normalized container (dict, list, or original value if not a container)

    Examples:
        >>> from collections import OrderedDict
        >>> normalize_json_container(OrderedDict([('a', 1)]))
        {'a': 1}

        >>> normalize_json_container("string")
        'string'
    """
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return list(value)
    return value


def prepare_json_payload(value: Any, *, default: Any | None = None) -> Any | None:
    """Prepare a value for storage as a JSON field.

    Handles bytes decoding, string parsing, and normalization to ensure
    the value can be safely stored in a JSON column.

    Args:
        value: The value to prepare
        default: Default value if input is None

    Returns:
        Prepared value ready for database storage, or None

    Examples:
        >>> prepare_json_payload({"key": "value"})
        {'key': 'value'}

        >>> prepare_json_payload(None, default={})
        {}

        >>> prepare_json_payload(b'{"key": "value"}')
        {'key': 'value'}
    """
    if value is None:
        value = default
    if value is None:
        return None

    # Handle memoryview
    if isinstance(value, memoryview):
        value = value.tobytes()

    # Handle bytes
    if isinstance(value, bytes | bytearray):
        try:
            value = value.decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            value = value.decode("utf-8", errors="replace")

    # Handle string input - try to parse as JSON
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return stripped

    # Normalize containers
    normalized = normalize_json_container(value)

    # Verify it's JSON-serializable
    try:
        json.dumps(normalized)
        return normalized
    except (TypeError, ValueError):
        # Try coercing with default=str
        try:
            coerced = json.loads(json.dumps(normalized, default=str))
        except (TypeError, ValueError):
            return None
        return coerced
