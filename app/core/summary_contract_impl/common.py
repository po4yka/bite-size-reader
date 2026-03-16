from __future__ import annotations

from typing import Any

SummaryJSON = dict[str, Any]


def is_numeric(value: Any) -> bool:
    """Check if a value can be converted to a float."""
    if value is None:
        return False
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def clean_string_list(values: Any, *, limit: int | None = None) -> list[str]:
    if values is None:
        return []
    result: list[str] = []
    seen: set[str] = set()
    iterable = list(values) if isinstance(values, list | tuple | set) else [values]
    for item in iterable:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result
