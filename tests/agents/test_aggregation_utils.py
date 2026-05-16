"""Unit tests for aggregation utility functions."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.agents._aggregation_utils import (
    _canonical_sentence,
    _clean_string_list,
    _coerce_int,
    _filter_source_item_ids,
    _has_image_evidence,
    _has_metadata_evidence,
    _has_ocr_evidence,
    _has_text_evidence,
    _has_transcript_evidence,
    _normalize_tags,
    _numeric_sentence_base,
    _parse_evidence_kinds,
    _select_metadata,
    _truncate,
)
from app.application.dto.aggregation import AggregationEvidenceKind, ExtractedTextKind


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_string_unchanged(self):
        assert _truncate("hello", 10) == "hello"

    def test_exact_length_unchanged(self):
        assert _truncate("hello", 5) == "hello"

    def test_long_string_truncated_with_ellipsis(self):
        result = _truncate("hello world", 8)
        assert result.endswith("…")
        assert len(result) <= 8

    def test_strips_leading_trailing_whitespace(self):
        assert _truncate("  hello  ", 20) == "hello"

    def test_empty_string(self):
        assert _truncate("", 10) == ""


# ---------------------------------------------------------------------------
# _coerce_int
# ---------------------------------------------------------------------------


class TestCoerceInt:
    def test_int_input(self):
        assert _coerce_int(5) == 5

    def test_string_int(self):
        assert _coerce_int("10") == 10

    def test_float_truncates(self):
        assert _coerce_int(3.9) == 3

    def test_none_returns_none(self):
        assert _coerce_int(None) is None

    def test_non_numeric_string_returns_none(self):
        assert _coerce_int("abc") is None

    def test_negative_returns_none(self):
        assert _coerce_int(-1) is None

    def test_zero_is_valid(self):
        assert _coerce_int(0) == 0


# ---------------------------------------------------------------------------
# _canonical_sentence
# ---------------------------------------------------------------------------


class TestCanonicalSentence:
    def test_lowercases(self):
        assert _canonical_sentence("Hello World") == "hello world"

    def test_removes_punctuation(self):
        result = _canonical_sentence("Hello, world!")
        assert "," not in result
        assert "!" not in result

    def test_collapses_whitespace(self):
        result = _canonical_sentence("hello   world")
        assert "  " not in result

    def test_empty_string(self):
        assert _canonical_sentence("") == ""


# ---------------------------------------------------------------------------
# _numeric_sentence_base
# ---------------------------------------------------------------------------


class TestNumericSentenceBase:
    def test_replaces_numbers(self):
        result = _numeric_sentence_base("The price is 100 dollars")
        assert "100" not in result

    def test_removes_stopwords(self):
        result = _numeric_sentence_base("The price is high")
        assert "the" not in result
        assert "is" not in result

    def test_returns_string(self):
        assert isinstance(_numeric_sentence_base("hello world"), str)


# ---------------------------------------------------------------------------
# _clean_string_list
# ---------------------------------------------------------------------------


class TestCleanStringList:
    def test_deduplicates(self):
        result = _clean_string_list(["a", "b", "a"])
        assert result == ["a", "b"]

    def test_strips_whitespace(self):
        result = _clean_string_list(["  hello  "])
        assert result == ["hello"]

    def test_filters_empty_strings(self):
        result = _clean_string_list(["a", "", "  ", "b"])
        assert "" not in result
        assert "  " not in result

    def test_non_list_returns_empty(self):
        assert _clean_string_list(None) == []
        assert _clean_string_list("string") == []

    def test_converts_to_str(self):
        result = _clean_string_list([1, 2, 3])
        assert result == ["1", "2", "3"]


# ---------------------------------------------------------------------------
# _normalize_tags
# ---------------------------------------------------------------------------


class TestNormalizeTags:
    def test_adds_hash_prefix(self):
        result = _normalize_tags(["python"])
        assert "#python" in result

    def test_lowercases(self):
        result = _normalize_tags(["Python", "AI"])
        assert "#python" in result
        assert "#ai" in result

    def test_deduplicates(self):
        result = _normalize_tags(["python", "#python"])
        assert result.count("#python") == 1

    def test_limits_to_15(self):
        tags = [f"tag{i}" for i in range(20)]
        result = _normalize_tags(tags)
        assert len(result) <= 15

    def test_non_list_returns_empty(self):
        assert _normalize_tags(None) == []


# ---------------------------------------------------------------------------
# _select_metadata
# ---------------------------------------------------------------------------


class TestSelectMetadata:
    def test_selects_known_keys(self):
        metadata = {"author": "Alice", "channel": "test", "unknown": "value"}
        result = _select_metadata(metadata)
        assert "author" in result
        assert "channel" in result
        assert "unknown" not in result

    def test_includes_topic_tags(self):
        metadata = {"topic_tags": ["#ai"]}
        result = _select_metadata(metadata)
        assert "topic_tags" in result

    def test_includes_entities(self):
        metadata = {"entities": [{"name": "Alice"}]}
        result = _select_metadata(metadata)
        assert "entities" in result

    def test_empty_metadata(self):
        assert _select_metadata({}) == {}


# ---------------------------------------------------------------------------
# Evidence detection helpers
# ---------------------------------------------------------------------------


def _make_doc(
    text: str = "",
    text_blocks: list[Any] | None = None,
    media: list[Any] | None = None,
    metadata: dict[str, Any] | None = None,
    title: str = "",
) -> Any:
    doc = MagicMock()
    doc.text = text
    doc.text_blocks = text_blocks or []
    doc.media = media or []
    doc.metadata = metadata or {}
    doc.title = title
    doc.provenance = MagicMock()
    doc.provenance.external_id = None
    return doc


def _make_block(kind: ExtractedTextKind, text: str = "hello") -> Any:
    block = MagicMock()
    block.kind = kind
    block.text = text
    return block


class TestHasTextEvidence:
    def test_body_block(self):
        doc = _make_doc(text_blocks=[_make_block(ExtractedTextKind.BODY)])
        assert _has_text_evidence(doc) is True

    def test_caption_block(self):
        doc = _make_doc(text_blocks=[_make_block(ExtractedTextKind.CAPTION)])
        assert _has_text_evidence(doc) is True

    def test_title_block(self):
        doc = _make_doc(text_blocks=[_make_block(ExtractedTextKind.TITLE)])
        assert _has_text_evidence(doc) is True

    def test_plain_text_field(self):
        doc = _make_doc(text="Some content")
        assert _has_text_evidence(doc) is True

    def test_no_text_evidence(self):
        doc = _make_doc()
        assert _has_text_evidence(doc) is False

    def test_none_document(self):
        assert _has_text_evidence(None) is False


class TestHasTranscriptEvidence:
    def test_transcript_block(self):
        doc = _make_doc(text_blocks=[_make_block(ExtractedTextKind.TRANSCRIPT)])
        assert _has_transcript_evidence(doc) is True

    def test_no_transcript(self):
        doc = _make_doc(text_blocks=[_make_block(ExtractedTextKind.BODY)])
        assert _has_transcript_evidence(doc) is False

    def test_none_document(self):
        assert _has_transcript_evidence(None) is False


class TestHasOcrEvidence:
    def test_ocr_block(self):
        doc = _make_doc(text_blocks=[_make_block(ExtractedTextKind.OCR)])
        assert _has_ocr_evidence(doc) is True

    def test_no_ocr(self):
        doc = _make_doc()
        assert _has_ocr_evidence(doc) is False

    def test_none_document(self):
        assert _has_ocr_evidence(None) is False


class TestHasImageEvidence:
    def test_with_media(self):
        doc = _make_doc(media=[MagicMock()])
        assert _has_image_evidence(doc) is True

    def test_no_media(self):
        doc = _make_doc()
        assert _has_image_evidence(doc) is False

    def test_none_document(self):
        assert _has_image_evidence(None) is False


class TestHasMetadataEvidence:
    def test_with_metadata(self):
        doc = _make_doc(metadata={"author": "Alice"})
        assert _has_metadata_evidence(doc) is True

    def test_with_title(self):
        doc = _make_doc(title="My Article")
        assert _has_metadata_evidence(doc) is True

    def test_with_external_id(self):
        doc = _make_doc()
        doc.provenance.external_id = "ext-123"
        assert _has_metadata_evidence(doc) is True

    def test_no_evidence(self):
        doc = _make_doc()
        assert _has_metadata_evidence(doc) is False

    def test_none_document(self):
        assert _has_metadata_evidence(None) is False


# ---------------------------------------------------------------------------
# _parse_evidence_kinds
# ---------------------------------------------------------------------------


class TestParseEvidenceKinds:
    def test_valid_kinds(self):
        result = _parse_evidence_kinds(["text", "transcript"])
        assert AggregationEvidenceKind.TEXT in result
        assert AggregationEvidenceKind.TRANSCRIPT in result

    def test_invalid_kinds_skipped(self):
        result = _parse_evidence_kinds(["text", "invalid_kind"])
        assert len(result) == 1

    def test_deduplicates(self):
        result = _parse_evidence_kinds(["text", "text"])
        assert len(result) == 1

    def test_non_list_returns_empty(self):
        assert _parse_evidence_kinds(None) == []
        assert _parse_evidence_kinds("text") == []


# ---------------------------------------------------------------------------
# _filter_source_item_ids
# ---------------------------------------------------------------------------


class TestFilterSourceItemIds:
    def test_filters_to_valid_ids(self):
        result = _filter_source_item_ids(["a", "b", "c"], {"a", "c"})
        assert result == ["a", "c"]

    def test_deduplicates(self):
        result = _filter_source_item_ids(["a", "a"], {"a"})
        assert result == ["a"]

    def test_non_list_returns_empty(self):
        assert _filter_source_item_ids(None, {"a"}) == []

    def test_empty_valid_set(self):
        assert _filter_source_item_ids(["a", "b"], set()) == []
