"""Shared utilities for command handlers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def maybe_load_json(payload: Any) -> Any:
    """Return parsed JSON dict from payload (dict, bytes, str, or None)."""
    if payload is None:
        return None

    if isinstance(payload, Mapping):
        return dict(payload)

    if isinstance(payload, bytes | bytearray):
        try:
            payload = payload.decode("utf-8")
        except Exception:
            payload = payload.decode("utf-8", errors="replace")

    if isinstance(payload, str):
        stripped = payload.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return None

    return payload


def parse_command_arguments(
    text: str,
    command: str,
    *,
    max_parts: int | None = None,
) -> list[str]:
    """Strip command prefix and bot mention from text, return remaining args."""
    remainder = text[len(command) :] if text.startswith(command) else text

    remainder = remainder.lstrip()
    if remainder.startswith("@"):
        parts = remainder.split(maxsplit=1)
        remainder = parts[1] if len(parts) > 1 else ""

    remainder = remainder.strip()
    if not remainder:
        return []

    if max_parts is not None:
        return remainder.split(maxsplit=max_parts - 1)
    return remainder.split()


def truncate_text(text: str, max_length: int, *, suffix: str = "...") -> str:
    """Return text clamped to max_length, appending suffix when truncated."""
    if len(text) <= max_length:
        return text

    truncate_at = max_length - len(suffix)
    if truncate_at <= 0:
        return suffix[:max_length]

    return text[:truncate_at] + suffix
