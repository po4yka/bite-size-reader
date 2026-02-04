"""Pure text utilities with no domain knowledge.

These are general-purpose string manipulation helpers used across the codebase.
Extracted from summary_contract.py to eliminate duplication in summary_schema.py
and provide a single import point.
"""

from __future__ import annotations

import difflib
from typing import Any


def cap_text(text: str, limit: int) -> str:
    """Cap *text* to *limit* characters, trimming at a sentence boundary."""
    # Security: Validate inputs
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    if not isinstance(limit, int) or limit <= 0:
        msg = "Limit must be a positive integer"
        raise ValueError(msg)

    # Security: Prevent extremely large limits
    if limit > 10000:
        msg = "Limit too large"
        raise ValueError(msg)

    if len(text) <= limit:
        return text
    # cut to limit and then trim to last sentence/phrase boundary
    snippet = text[:limit]
    for sep in (". ", "! ", "? ", "; ", ", "):
        idx = snippet.rfind(sep)
        if idx > 0:
            return snippet[: idx + len(sep)].strip()
    return snippet.strip()


def normalize_whitespace(text: str) -> str:
    """Collapse multiple whitespace characters into a single space."""
    if not isinstance(text, str):
        return ""
    return " ".join(text.split()).strip()


def similarity_ratio(text_a: str, text_b: str) -> float:
    """Compute Levenshtein-style similarity ratio between two strings."""
    if not text_a or not text_b:
        return 0.0
    return difflib.SequenceMatcher(None, text_a, text_b).ratio()


def is_numeric(value: Any) -> bool:
    """Check if a value can be converted to a float."""
    if value is None:
        return False
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def dedupe_case_insensitive(items: list[str]) -> list[str]:
    """Remove duplicates case-insensitively with security validation."""
    # Security: Validate inputs
    if not isinstance(items, list):
        return []

    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if not isinstance(it, str):
            continue
        key = it.strip().lower()
        if key and key not in seen:
            # Security: Prevent extremely long items
            if len(key) > 500:
                continue
            # Security: Prevent dangerous content
            if any(char in key for char in ["<", ">", "script", "javascript"]):
                continue
            seen.add(key)
            out.append(it.strip())
    return out


def clean_string_list(values: Any, *, limit: int | None = None) -> list[str]:
    """Normalize and deduplicate a list of strings."""
    if values is None:
        return []
    result: list[str] = []
    seen: set[str] = set()
    iterable: list[Any]
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


def hash_tagify(tags: list[str], max_tags: int = 10) -> list[str]:
    """Deduplicate tags, enforce ``#`` prefix, and cap count."""
    # Security: Validate inputs
    if not isinstance(tags, list):
        return []
    if not isinstance(max_tags, int) or max_tags <= 0 or max_tags > 100:
        max_tags = 10

    seen: set[str] = set()
    result: list[str] = []
    for t in tags:
        if not isinstance(t, str):
            continue
        t = t.strip()
        if not t:
            continue
        # Security: Prevent extremely long tags
        if len(t) > 100:
            continue
        # Security: Prevent dangerous content in tags
        if any(char in t.lower() for char in ["<", ">", "script", "javascript"]):
            continue

        if not t.startswith("#"):
            t = f"#{t}"
        key = t.lower()
        if key not in seen:
            seen.add(key)
            result.append(t)
        if len(result) >= max_tags:
            break
    return result
