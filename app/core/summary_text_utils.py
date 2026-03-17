"""Shared text shaping helpers for summary contracts and schemas."""

from __future__ import annotations


def cap_text(text: str, limit: int) -> str:
    """Cap text to ``limit`` characters, trimming at a phrase boundary."""
    if not isinstance(limit, int) or limit <= 0:
        msg = "Limit must be a positive integer"
        raise ValueError(msg)
    if limit > 10000:
        msg = "Limit too large"
        raise ValueError(msg)
    if len(text) <= limit:
        return text

    snippet = text[:limit]
    for sep in (". ", "! ", "? ", "; ", ", "):
        idx = snippet.rfind(sep)
        if idx > 0:
            return snippet[: idx + len(sep)].strip()
    return snippet.strip()


def hash_tagify(tags: list[str], max_tags: int = 10) -> list[str]:
    """Deduplicate tags, enforce # prefix, and cap count."""
    if not isinstance(tags, list):
        return []
    if not isinstance(max_tags, int) or max_tags <= 0 or max_tags > 100:
        max_tags = 10

    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            continue
        tag = tag.strip()
        if not tag:
            continue
        if len(tag) > 100:
            continue
        if any(char in tag.lower() for char in ["<", ">", "script", "javascript"]):
            continue
        if not tag.startswith("#"):
            tag = f"#{tag}"
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            result.append(tag)
        if len(result) >= max_tags:
            break
    return result


def dedupe_case_insensitive(items: list[str]) -> list[str]:
    """Return case-insensitive deduplicated list while preserving order."""
    if not isinstance(items, list):
        return []

    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        key = item.strip().lower()
        if key and key not in seen:
            if len(key) > 500:
                continue
            if any(char in key for char in ["<", ">", "script", "javascript"]):
                continue
            seen.add(key)
            output.append(item.strip())
    return output
