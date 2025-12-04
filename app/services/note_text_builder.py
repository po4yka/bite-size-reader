"""Helpers for constructing note text and metadata for embeddings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.embedding_service import prepare_text_for_embedding


@dataclass(frozen=True)
class NoteText:
    """Container for note text and associated metadata."""

    text: str
    metadata: dict[str, Any]


def build_note_text(
    payload: dict[str, Any] | None,
    *,
    request_id: int | None,
    summary_id: int | None,
    language: str | None,
    user_note: str | None = None,
    max_length: int = 512,
) -> NoteText:
    """Build combined note text from summary payload and user input.

    The base text uses :func:`prepare_text_for_embedding` to preserve the
    weighting and truncation semantics already used for summary embeddings.
    Optional user-provided notes are appended to that base text.

    Args:
        payload: Summary payload containing summary fields and metadata.
        request_id: Request identifier associated with the summary.
        summary_id: Summary identifier associated with the payload.
        language: Language code to store alongside the note for filtering.
        user_note: Optional free-form text supplied by the user.
        max_length: Maximum token approximation passed to the embedding helper.

    Returns:
        NoteText with combined text and metadata suitable for Chroma filters.
    """

    payload = payload or {}
    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}

    topic_tags = _extract_tags(payload, metadata)

    summary_text = prepare_text_for_embedding(
        title=metadata.get("title") or payload.get("title"),
        summary_1000=payload.get("summary_1000"),
        summary_250=payload.get("summary_250"),
        tldr=payload.get("tldr"),
        key_ideas=payload.get("key_ideas"),
        topic_tags=topic_tags,
        max_length=max_length,
    )

    combined_text = _combine_summary_and_notes(
        summary_text=summary_text,
        user_note=user_note,
        max_length=max_length,
    )

    note_metadata = {
        "request_id": request_id,
        "summary_id": summary_id,
        "language": language,
        "tags": topic_tags,
    }

    return NoteText(text=combined_text, metadata=note_metadata)


def _extract_tags(payload: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    """Collect and normalize tags from payload and metadata."""

    raw_tag_sources: list[list[Any]] = []

    for candidate in (payload.get("topic_tags"), metadata.get("tags")):
        if isinstance(candidate, (list, tuple, set)):
            raw_tag_sources.append(list(candidate))

    clean_tags: list[str] = []
    seen: set[str] = set()

    for source in raw_tag_sources:
        for tag in source:
            cleaned = str(tag).strip().lstrip("#")
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                clean_tags.append(cleaned)

    return clean_tags


def _combine_summary_and_notes(
    *,
    summary_text: str,
    user_note: str | None,
    max_length: int,
) -> str:
    """Append user notes to summary-derived text with truncation."""

    parts = []
    if summary_text and summary_text.strip():
        parts.append(summary_text.strip())

    if user_note:
        note_text = str(user_note).strip()
        if note_text:
            parts.append(note_text)

    combined = " ".join(parts).strip()

    if combined and len(combined) > max_length * 4:
        combined = combined[: max_length * 4]

    return combined
