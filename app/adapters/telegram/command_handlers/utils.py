"""Shared utilities for command handlers.

This module contains utility functions used across multiple command handlers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def maybe_load_json(payload: Any) -> Any:
    """Load JSON from various formats.

    This function handles JSON payloads that may come in different forms:
    - Already parsed dictionaries/mappings
    - Raw bytes or bytearray
    - JSON strings
    - None values

    Args:
        payload: The input payload in any format.

    Returns:
        The parsed JSON data, or None if parsing fails or input is empty.

    Example:
        >>> maybe_load_json('{"key": "value"}')
        {'key': 'value'}
        >>> maybe_load_json(b'{"key": "value"}')
        {'key': 'value'}
        >>> maybe_load_json({'key': 'value'})
        {'key': 'value'}
        >>> maybe_load_json(None)
        None
    """
    if payload is None:
        return None

    # Already a mapping (dict-like)
    if isinstance(payload, Mapping):
        return dict(payload)

    # Bytes or bytearray - decode to string first
    if isinstance(payload, bytes | bytearray):
        try:
            payload = payload.decode("utf-8")
        except Exception:
            payload = payload.decode("utf-8", errors="replace")

    # String - try to parse as JSON
    if isinstance(payload, str):
        stripped = payload.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return None

    # Unknown type - return as-is
    return payload


def parse_command_arguments(
    text: str,
    command: str,
    *,
    max_parts: int | None = None,
) -> list[str]:
    """Parse arguments from a command string.

    This function strips the command prefix and optional bot mention,
    then splits the remaining text into arguments.

    Args:
        text: The full message text (e.g., "/command@bot arg1 arg2").
        command: The command prefix to strip (e.g., "/command").
        max_parts: Maximum number of parts to split into.

    Returns:
        List of argument strings (may be empty).

    Example:
        >>> parse_command_arguments("/read 123", "/read")
        ['123']
        >>> parse_command_arguments("/unread@mybot 5 tech", "/unread")
        ['5', 'tech']
    """
    # Strip the command prefix
    remainder = text[len(command) :] if text.startswith(command) else text

    # Strip optional bot mention (e.g., "@botname")
    remainder = remainder.lstrip()
    if remainder.startswith("@"):
        parts = remainder.split(maxsplit=1)
        remainder = parts[1] if len(parts) > 1 else ""

    # Split into arguments
    remainder = remainder.strip()
    if not remainder:
        return []

    if max_parts is not None:
        return remainder.split(maxsplit=max_parts - 1)
    return remainder.split()


def truncate_text(text: str, max_length: int, *, suffix: str = "...") -> str:
    """Truncate text to a maximum length with a suffix.

    Args:
        text: The text to truncate.
        max_length: Maximum length including suffix.
        suffix: String to append when truncating.

    Returns:
        Truncated text, or original if already short enough.

    Example:
        >>> truncate_text("Hello, World!", 10)
        'Hello, ...'
    """
    if len(text) <= max_length:
        return text

    # Account for suffix length
    truncate_at = max_length - len(suffix)
    if truncate_at <= 0:
        return suffix[:max_length]

    return text[:truncate_at] + suffix
