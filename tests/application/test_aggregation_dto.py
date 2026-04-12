"""Tests for aggregation DTOs and normalized extractor contracts."""

from __future__ import annotations

import pytest

from app.application.dto.aggregation import (
    AggregatedClaim,
    AggregationEvidenceKind,
    AggregationFailure,
    AggregationRelationshipSignal,
    ExtractedTextKind,
    MultiSourceAggregationOutput,
    NormalizedSourceDocument,
    SourceMediaAsset,
    SourceMediaKind,
    SourceProvenance,
)
from app.domain.models.source import SourceItem, SourceKind


def test_normalized_source_document_from_extracted_content() -> None:
    source_item = SourceItem.create(
        kind=SourceKind.YOUTUBE_VIDEO,
        original_value="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        external_id="dQw4w9WgXcQ",
    )

    document = NormalizedSourceDocument.from_extracted_content(
        source_item=source_item,
        text="Transcript body",
        title="Never Gonna Give You Up",
        detected_language="en",
        content_source="youtube-transcript-api",
        media_urls=["https://img.youtube.com/vi/dQw4w9WgXcQ/default.jpg"],
        text_kind=ExtractedTextKind.TRANSCRIPT,
        metadata={"channel": "RickAstleyVEVO"},
    )

    assert document.source_kind == SourceKind.YOUTUBE_VIDEO
    assert document.text == "Transcript body"
    assert document.text_blocks[1].kind == ExtractedTextKind.TRANSCRIPT
    assert document.media[0].kind == SourceMediaKind.IMAGE
    assert document.provenance.external_id == "dQw4w9WgXcQ"


def test_normalized_source_document_preserves_structured_media_assets() -> None:
    source_item = SourceItem.create(
        kind=SourceKind.X_POST,
        original_value="https://x.com/user/status/123",
        external_id="123",
    )

    document = NormalizedSourceDocument.from_extracted_content(
        source_item=source_item,
        text="Tweet body",
        content_source="twitter_graphql",
        media_assets=[
            SourceMediaAsset(
                kind=SourceMediaKind.IMAGE,
                url="https://pbs.twimg.com/media/chart.jpg",
                alt_text="Quarterly revenue chart",
            )
        ],
    )

    assert document.media[0].url == "https://pbs.twimg.com/media/chart.jpg"
    assert document.media[0].alt_text == "Quarterly revenue chart"
    assert document.media[0].position == 0


def test_normalized_source_document_rejects_empty_payload() -> None:
    source_item = SourceItem.create(
        kind=SourceKind.WEB_ARTICLE,
        original_value="https://example.com/post",
    )

    with pytest.raises(ValueError, match="require extracted text or media"):
        NormalizedSourceDocument(
            source_item_id=source_item.stable_id,
            source_kind=source_item.kind,
            provenance=SourceProvenance(
                source_item_id=source_item.stable_id,
                source_kind=source_item.kind,
            ),
        )


def test_source_media_asset_requires_locator() -> None:
    with pytest.raises(ValueError, match="require either a URL or a local path"):
        SourceMediaAsset(kind=SourceMediaKind.IMAGE)


def test_aggregation_failure_defaults() -> None:
    failure = AggregationFailure(code="extract_timeout", message="Timed out")

    assert failure.retryable is False
    assert failure.details == {}


def test_aggregation_relationship_signal_from_batch_output() -> None:
    class _SeriesInfo:
        def model_dump(self) -> dict[str, object]:
            return {"article_order": [1, 2], "series_title": "Series"}

    class _Relationship:
        relationship_type = "topic_cluster"
        confidence = 0.82
        reasoning = "Shared entities"
        signals_used = ["entity_overlap"]
        series_info = _SeriesInfo()
        cluster_info = None

    relationship = AggregationRelationshipSignal.from_relationship_analysis(_Relationship())

    assert relationship.relationship_type == "topic_cluster"
    assert relationship.confidence == pytest.approx(0.82)
    assert relationship.metadata["series_info"]["series_title"] == "Series"


def test_multi_source_aggregation_output_requires_overview() -> None:
    with pytest.raises(ValueError, match="non-empty overview"):
        MultiSourceAggregationOutput(
            session_id=1,
            correlation_id="agg-7",
            status="completed",
            source_type="mixed",
            total_items=2,
            extracted_items=2,
            used_source_count=1,
            overview="  ",
        )


def test_aggregated_claim_requires_text_and_provenance() -> None:
    claim = AggregatedClaim(
        claim_id="claim_1",
        text="Revenue figures differ across the bundle.",
        source_item_ids=["src_one", "src_two"],
        evidence_kinds=[AggregationEvidenceKind.TEXT, AggregationEvidenceKind.METADATA],
        confidence=0.6,
    )

    assert claim.claim_id == "claim_1"
    assert claim.source_item_ids == ["src_one", "src_two"]
