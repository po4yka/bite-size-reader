"""Utility helpers shared by topic search services and index builders."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TopicSearchDocument:
    """Precomputed representation of a summary suitable for indexing."""

    request_id: int
    url: str | None
    title: str | None
    snippet: str | None
    source: str | None
    published_at: str | None
    body: str
    tags_text: str | None


def ensure_mapping(value: Any) -> dict[str, Any]:
    """Return a mapping for JSON-like data, gracefully handling text payloads."""
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(loaded, Mapping):
            return dict(loaded)
    return {}


def normalize_text(value: Any) -> str | None:
    """Normalize primitive values into trimmed text suitable for display."""
    if value is None:
        return None
    if isinstance(value, int | float):
        value = str(value)
    text = str(value).strip()
    return text or None


def clean_snippet(snippet: str | None, *, limit: int = 300) -> str | None:
    """Normalize snippet text into a compact preview."""
    if not snippet:
        return None
    compact = " ".join(snippet.split())
    if not compact:
        return None
    if len(compact) > limit:
        compact = compact[: limit - 3].rstrip() + "..."
    return compact


def build_snippet(payload: Mapping[str, Any]) -> str | None:
    """Return the best available short summary snippet from a payload."""
    for key in ("summary_250", "summary_1000", "tldr"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return clean_snippet(value)
    return None


def tokenize(query: str) -> list[str]:
    """Split a query into normalized search terms."""
    return [piece for piece in re.findall(r"[\w-]+", query.casefold()) if piece]


def _append_metadata_values(parts: list[str], value: Any) -> None:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        parts.extend(str(item) for item in value if item)
    elif isinstance(value, str):
        parts.append(value)


def compose_search_body(
    *,
    title: str | None,
    payload: Mapping[str, Any],
    metadata: Mapping[str, Any],
    content_text: str | None,
) -> tuple[str, str | None]:
    """Compose a lower-cased document body and tag text for indexing/search."""
    parts: list[str] = []
    if title:
        parts.append(title)

    for key in ("summary_250", "summary_1000", "tldr"):
        value = payload.get(key)
        if isinstance(value, str):
            parts.append(value)

    tag_values: list[str] = []
    topic_tags = payload.get("topic_tags")
    if isinstance(topic_tags, Sequence) and not isinstance(topic_tags, str | bytes | bytearray):
        for tag in topic_tags:
            if not tag:
                continue
            tag_text = normalize_text(tag)
            if not tag_text:
                continue
            tag_values.append(tag_text)
            parts.append(tag_text)

    metadata_values: Iterable[Any] = (
        metadata.get("description"),
        metadata.get("keywords"),
        metadata.get("section"),
    )
    for value in metadata_values:
        _append_metadata_values(parts, value)

    if isinstance(content_text, str):
        parts.append(content_text)

    normalized = " ".join(str(part) for part in parts if part)
    tags_text = " ".join(tag_values) if tag_values else None
    return normalized.casefold(), tags_text


def build_topic_search_document(
    *,
    request_id: int,
    payload: Mapping[str, Any],
    request_data: Mapping[str, Any],
) -> TopicSearchDocument | None:
    """Create a document payload for indexing from a stored summary."""
    metadata = ensure_mapping(payload.get("metadata"))

    url = (
        normalize_text(metadata.get("canonical_url"))
        or normalize_text(metadata.get("url"))
        or normalize_text(request_data.get("normalized_url"))
        or normalize_text(request_data.get("input_url"))
    )
    if not url:
        return None

    title = normalize_text(metadata.get("title")) or normalize_text(payload.get("title")) or url

    body, tags_text = compose_search_body(
        title=title,
        payload=payload,
        metadata=metadata,
        content_text=normalize_text(request_data.get("content_text")),
    )
    if not body.strip():
        return None

    snippet = build_snippet(payload)
    source = normalize_text(metadata.get("domain") or metadata.get("source"))
    published = normalize_text(
        metadata.get("published_at") or metadata.get("published") or metadata.get("last_updated")
    )

    return TopicSearchDocument(
        request_id=request_id,
        url=url,
        title=title,
        snippet=snippet,
        source=source,
        published_at=published,
        body=body,
        tags_text=tags_text,
    )
