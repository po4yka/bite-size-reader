"""Text helpers for LLM summarization."""

from __future__ import annotations

import re
from typing import Any

_STRING_LIST_SPLITTER_RE = re.compile(r"[,;|\n]+")


def coerce_string_list(value: Any) -> list[str]:
    """Coerce arbitrary list-like structures into a list of clean strings."""
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, list | tuple):
                nested = coerce_string_list(list(item))
                result.extend(nested)
                continue
            if isinstance(item, dict):
                parts = [str(v).strip() for v in item.values() if str(v).strip()]
                if parts:
                    result.append(" ".join(parts))
                continue
            text = str(item).strip()
            if text:
                result.append(text)
        return result

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        parts = [part.strip(" -•\t") for part in _STRING_LIST_SPLITTER_RE.split(cleaned)]
        return [part for part in parts if part]

    if value is None:
        return []

    text = str(value).strip()
    return [text] if text else []


def truncate_content_text(content_text: str, max_chars: int) -> str:
    """Truncate text on natural boundaries where possible."""
    if len(content_text) <= max_chars:
        return content_text
    snippet = content_text[:max_chars]
    for sep in ("\n\n", "\n", ". ", "? ", "! "):
        idx = snippet.rfind(sep)
        if idx > max_chars * 0.6:
            return snippet[: idx + len(sep)].strip()
    return snippet.strip()
