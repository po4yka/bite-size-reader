"""Shared text preparation for semantic embedding workflows."""

from __future__ import annotations

from typing import Any


def prepare_text_for_embedding(
    *,
    title: str | None,
    summary_1000: str | None,
    summary_250: str | None,
    tldr: str | None,
    key_ideas: list[str] | None = None,
    topic_tags: list[str] | None = None,
    semantic_boosters: list[str] | None = None,
    query_expansion_keywords: list[str] | None = None,
    semantic_chunks: list[dict[str, Any]] | None = None,
    max_length: int = 512,
) -> str:
    """Compose a single semantic text block suitable for embedding generation."""
    parts: list[str] = []

    if title:
        parts.append(title)
        parts.append(title)

    if summary_1000:
        parts.append(summary_1000)
    elif summary_250:
        parts.append(summary_250)
    elif tldr:
        parts.append(tldr)

    if key_ideas:
        parts.extend(key_ideas[:5])

    if topic_tags:
        parts.extend(tag.lstrip("#") for tag in topic_tags[:5])

    if semantic_boosters:
        parts.extend(semantic_boosters[:10])

    if semantic_chunks:
        for chunk in semantic_chunks[:6]:
            if not isinstance(chunk, dict):
                continue
            text = chunk.get("text")
            if text:
                parts.append(str(text))
            local_summary = chunk.get("local_summary")
            if local_summary:
                parts.append(str(local_summary))
            local_keywords = chunk.get("local_keywords") or []
            if isinstance(local_keywords, list):
                parts.extend(str(keyword) for keyword in local_keywords[:3] if str(keyword).strip())

    if query_expansion_keywords:
        parts.extend(query_expansion_keywords[:10])

    text = " ".join(parts)
    if len(text) > max_length * 4:
        text = text[: max_length * 4]
    return text.strip()
