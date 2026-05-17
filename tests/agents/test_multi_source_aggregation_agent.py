"""Focused tests for multi-source aggregation heuristics."""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.agents.multi_source_aggregation_agent import (
    MultiSourceAggregationAgent,
    _SentenceCache,
)
from app.application.dto.aggregation import (
    ExtractedTextKind,
    NormalizedSourceDocument,
    SourceExtractionItemResult,
    SourceProvenance,
    SourceTextBlock,
)
from app.domain.models.source import AggregationItemStatus, SourceKind


def _agent() -> MultiSourceAggregationAgent:
    return MultiSourceAggregationAgent(aggregation_session_repo=AsyncMock())


def _document(
    source_item_id: str,
    text: str,
    *,
    title: str | None = None,
    kind: SourceKind = SourceKind.WEB_ARTICLE,
) -> NormalizedSourceDocument:
    return NormalizedSourceDocument(
        source_item_id=source_item_id,
        source_kind=kind,
        title=title,
        text=text,
        text_blocks=[
            SourceTextBlock(
                kind=ExtractedTextKind.BODY,
                text=text,
                position=0,
            )
        ],
        provenance=SourceProvenance(
            source_item_id=source_item_id,
            source_kind=kind,
        ),
    )


def _item(position: int, document: NormalizedSourceDocument) -> SourceExtractionItemResult:
    return SourceExtractionItemResult(
        position=position,
        item_id=position,
        source_item_id=document.source_item_id,
        source_kind=document.source_kind,
        status=AggregationItemStatus.EXTRACTED.value,
        normalized_document=document,
    )


def test_sentence_cache_reuses_document_splits_across_heuristics() -> None:
    agent = _agent()
    shared_sentence = "Shared operational signal confirms the same account migration window."
    items = [
        _item(
            1,
            _document(
                "src_one",
                f"{shared_sentence} The rollout affected 12 customer accounts today.",
            ),
        ),
        _item(
            2,
            _document(
                "src_two",
                f"{shared_sentence} The rollout affected 18 customer accounts today.",
            ),
        ),
    ]
    source_weights = [agent._build_source_weight(item) for item in items]
    sentence_cache = _SentenceCache()

    duplicate_signals = agent._detect_duplicate_signals(
        items,
        sentence_cache=sentence_cache,
    )
    contradiction_hints = agent._detect_contradiction_hints(
        items,
        sentence_cache=sentence_cache,
    )
    fallback_claims = agent._fallback_claims(
        items,
        source_weights,
        sentence_cache=sentence_cache,
    )

    assert [signal.summary for signal in duplicate_signals] == [shared_sentence]
    assert duplicate_signals[0].source_item_ids == ["src_one", "src_two"]
    assert len(contradiction_hints) == 1
    assert contradiction_hints[0].source_item_ids == ["src_one", "src_two"]
    assert [claim.source_item_ids for claim in fallback_claims] == [["src_one"], ["src_two"]]
    assert len(sentence_cache._documents) == 2
    assert len(sentence_cache._blocks) == 2


def test_sentence_cache_keeps_distinct_documents_with_same_content() -> None:
    agent = _agent()
    text = "The same long enough sentence appears in two separate source documents."
    items = [
        _item(1, _document("src_one", text)),
        _item(2, _document("src_two", text)),
    ]
    sentence_cache = _SentenceCache()

    duplicate_signals = agent._detect_duplicate_signals(
        items,
        sentence_cache=sentence_cache,
    )

    assert duplicate_signals[0].source_item_ids == ["src_one", "src_two"]
    assert len(sentence_cache._documents) == 2
