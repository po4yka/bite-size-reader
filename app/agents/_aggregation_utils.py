"""Pure utility functions shared by aggregation agents."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.application.dto.aggregation import (
    AggregationEvidenceKind,
    AggregationEvidenceWeight,
    ExtractedTextKind,
)

if TYPE_CHECKING:
    from app.application.dto.aggregation import NormalizedSourceDocument

# ---------------------------------------------------------------------------
# Module-level compiled patterns and constants
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_NON_WORD_RE = re.compile(r"[^a-z0-9\s]+")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?%?")
_HASHTAG_RE = re.compile(r"(?<!\w)#([a-z0-9_-]+)", re.IGNORECASE)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "with",
}
_EVIDENCE_BASE_WEIGHTS: dict[AggregationEvidenceKind, float] = {
    AggregationEvidenceKind.TEXT: 1.0,
    AggregationEvidenceKind.TRANSCRIPT: 0.85,
    AggregationEvidenceKind.IMAGE: 0.6,
    AggregationEvidenceKind.OCR: 0.45,
    AggregationEvidenceKind.METADATA: 0.35,
}

# ---------------------------------------------------------------------------
# String utilities
# ---------------------------------------------------------------------------


def _truncate(value: str, max_length: int) -> str:
    stripped = value.strip()
    if len(stripped) <= max_length:
        return stripped
    return f"{stripped[: max_length - 1].rstrip()}…"


def _coerce_int(value: Any) -> int | None:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    return coerced if coerced >= 0 else None


def _canonical_sentence(sentence: str) -> str:
    lowered = sentence.lower()
    lowered = _NON_WORD_RE.sub(" ", lowered)
    return " ".join(lowered.split())


def _numeric_sentence_base(sentence: str) -> str:
    without_numbers = _NUMBER_RE.sub(" ", sentence.lower())
    without_numbers = _NON_WORD_RE.sub(" ", without_numbers)
    tokens = [token for token in without_numbers.split() if token not in _STOPWORDS]
    return " ".join(tokens)


def _clean_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _normalize_tags(values: Any) -> list[str]:
    tags: list[str] = []
    for value in _clean_string_list(values):
        normalized = value if value.startswith("#") else f"#{value}"
        normalized = normalized.lower()
        if normalized not in tags:
            tags.append(normalized)
    return tags[:15]


def _select_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "author",
        "channel",
        "published_at",
        "source",
        "content_source",
        "extraction_strategy",
        "quality_tier",
    )
    selected = {key: metadata[key] for key in keys if key in metadata}
    if "topic_tags" in metadata:
        selected["topic_tags"] = metadata["topic_tags"]
    if "entities" in metadata:
        selected["entities"] = metadata["entities"]
    return selected


# ---------------------------------------------------------------------------
# Document evidence detection
# ---------------------------------------------------------------------------


def _has_text_evidence(document: NormalizedSourceDocument | None) -> bool:
    if document is None:
        return False
    return any(
        block.kind in {ExtractedTextKind.BODY, ExtractedTextKind.CAPTION, ExtractedTextKind.TITLE}
        for block in document.text_blocks
    ) or bool(document.text.strip())


def _has_transcript_evidence(document: NormalizedSourceDocument | None) -> bool:
    if document is None:
        return False
    return any(block.kind == ExtractedTextKind.TRANSCRIPT for block in document.text_blocks)


def _has_ocr_evidence(document: NormalizedSourceDocument | None) -> bool:
    if document is None:
        return False
    return any(block.kind == ExtractedTextKind.OCR for block in document.text_blocks)


def _has_image_evidence(document: NormalizedSourceDocument | None) -> bool:
    if document is None:
        return False
    return bool(document.media)


def _has_metadata_evidence(document: NormalizedSourceDocument | None) -> bool:
    if document is None:
        return False
    return bool(document.metadata or document.title or document.provenance.external_id)


# ---------------------------------------------------------------------------
# LLM output parsing helpers
# ---------------------------------------------------------------------------


def _parse_evidence_kinds(raw_kinds: Any) -> list[AggregationEvidenceKind]:
    if not isinstance(raw_kinds, list):
        return []
    evidence_kinds: list[AggregationEvidenceKind] = []
    for raw_kind in raw_kinds:
        try:
            evidence_kind = AggregationEvidenceKind(str(raw_kind).strip().lower())
        except ValueError:
            continue
        if evidence_kind not in evidence_kinds:
            evidence_kinds.append(evidence_kind)
    return evidence_kinds


def _filter_source_item_ids(raw_source_ids: Any, valid_source_ids: set[str]) -> list[str]:
    if not isinstance(raw_source_ids, list):
        return []
    source_item_ids: list[str] = []
    for raw_source_id in raw_source_ids:
        source_item_id = str(raw_source_id).strip()
        if (
            source_item_id
            and source_item_id in valid_source_ids
            and source_item_id not in source_item_ids
        ):
            source_item_ids.append(source_item_id)
    return source_item_ids


__all__ = [
    "_EVIDENCE_BASE_WEIGHTS",
    "_HASHTAG_RE",
    "_NON_WORD_RE",
    "_NUMBER_RE",
    "_SENTENCE_SPLIT_RE",
    "_STOPWORDS",
    "_canonical_sentence",
    "_clean_string_list",
    "_coerce_int",
    "_filter_source_item_ids",
    "_has_image_evidence",
    "_has_metadata_evidence",
    "_has_ocr_evidence",
    "_has_text_evidence",
    "_has_transcript_evidence",
    "_normalize_tags",
    "_numeric_sentence_base",
    "_parse_evidence_kinds",
    "_select_metadata",
    "_truncate",
]
