"""JSON depth and size validation utilities."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Security limits for JSON parsing
MAX_JSON_SIZE = 10_000_000  # 10 MB
MAX_JSON_DEPTH = 20  # Maximum nesting depth
MAX_ARRAY_LENGTH = 10_000  # Maximum array length
MAX_DICT_KEYS = 1_000  # Maximum dictionary keys


class JSONValidationError(ValueError):
    """Raised when JSON validation fails."""

    pass


def calculate_json_depth(obj: Any, current_depth: int = 0, max_depth: int = 100) -> int:
    """Calculate the nesting depth of a JSON-like object.

    Args:
        obj: The object to analyze
        current_depth: Current depth in recursion
        max_depth: Maximum depth to prevent infinite recursion

    Returns:
        Maximum nesting depth

    Raises:
        JSONValidationError: If depth exceeds max_depth

    """
    if current_depth > max_depth:
        raise JSONValidationError(f"JSON depth exceeds maximum ({max_depth})")

    if isinstance(obj, dict):
        if not obj:
            return current_depth
        return max(
            (calculate_json_depth(v, current_depth + 1, max_depth) for v in obj.values()),
            default=current_depth,
        )
    elif isinstance(obj, list):
        if not obj:
            return current_depth
        return max(
            (calculate_json_depth(item, current_depth + 1, max_depth) for item in obj),
            default=current_depth,
        )
    return current_depth


def validate_json_structure(
    obj: Any,
    max_depth: int = MAX_JSON_DEPTH,
    max_array_length: int = MAX_ARRAY_LENGTH,
    max_dict_keys: int = MAX_DICT_KEYS,
) -> tuple[bool, str | None]:
    """Validate JSON structure against security constraints.

    Args:
        obj: The object to validate
        max_depth: Maximum nesting depth
        max_array_length: Maximum array length
        max_dict_keys: Maximum dictionary keys

    Returns:
        Tuple of (is_valid, error_message)

    """
    try:
        # Check depth
        depth = calculate_json_depth(obj, max_depth=max_depth)
        if depth > max_depth:
            return False, f"JSON depth ({depth}) exceeds maximum ({max_depth})"

        # Check array lengths and dict key counts
        def check_limits(o: Any, path: str = "root") -> tuple[bool, str | None]:
            if isinstance(o, dict):
                if len(o) > max_dict_keys:
                    return (
                        False,
                        f"Dictionary at {path} has {len(o)} keys, exceeds maximum ({max_dict_keys})",
                    )
                for key, value in o.items():
                    valid, error = check_limits(value, f"{path}.{key}")
                    if not valid:
                        return valid, error
            elif isinstance(o, list):
                if len(o) > max_array_length:
                    return (
                        False,
                        f"Array at {path} has {len(o)} items, exceeds maximum ({max_array_length})",
                    )
                for i, item in enumerate(o):
                    valid, error = check_limits(item, f"{path}[{i}]")
                    if not valid:
                        return valid, error
            return True, None

        return check_limits(obj)

    except JSONValidationError as e:
        return False, str(e)
    except RecursionError:
        return False, "JSON structure too deeply nested (recursion limit)"
    except Exception as e:
        logger.error(
            "json_validation_unexpected_error",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        return False, f"Unexpected error during validation: {e}"


def safe_json_parse(
    data: str,
    max_size: int = MAX_JSON_SIZE,
    max_depth: int = MAX_JSON_DEPTH,
    max_array_length: int = MAX_ARRAY_LENGTH,
    max_dict_keys: int = MAX_DICT_KEYS,
) -> tuple[Any | None, str | None]:
    """Safely parse JSON with validation.

    Args:
        data: JSON string to parse
        max_size: Maximum size in bytes
        max_depth: Maximum nesting depth
        max_array_length: Maximum array length
        max_dict_keys: Maximum dictionary keys

    Returns:
        Tuple of (parsed_object, error_message)

    """
    import json

    # Size check
    if len(data) > max_size:
        return None, f"JSON size ({len(data)} bytes) exceeds maximum ({max_size} bytes)"

    # Parse
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e.msg} at position {e.pos}"
    except Exception as e:
        return None, f"JSON parse error: {e}"

    # Validate structure
    valid, error = validate_json_structure(
        obj, max_depth=max_depth, max_array_length=max_array_length, max_dict_keys=max_dict_keys
    )

    if not valid:
        return None, error

    return obj, None
