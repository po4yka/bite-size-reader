"""Lightweight benchmarks for recently optimized pure-Python hot paths."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytest_benchmark = pytest.importorskip("pytest_benchmark")

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
from app.infrastructure.vector.point_ids import (
    repository_point_id,
    str_to_uuid,
    summary_point_id,
)


def _agent() -> MultiSourceAggregationAgent:
    return MultiSourceAggregationAgent(aggregation_session_repo=AsyncMock())


def _document(source_item_id: str, text: str, *, title: str) -> NormalizedSourceDocument:
    return NormalizedSourceDocument(
        source_item_id=source_item_id,
        source_kind=SourceKind.WEB_ARTICLE,
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
            source_kind=SourceKind.WEB_ARTICLE,
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


@pytest.fixture
def aggregation_items() -> list[SourceExtractionItemResult]:
    shared_signal = "Shared operational signal confirms the same migration window."
    items: list[SourceExtractionItemResult] = []
    for index in range(24):
        account_count = 100 + index
        source_id = f"source_{index:02d}"
        document = _document(
            source_id,
            (
                f"{shared_signal} "
                f"The migration affected {account_count} customer accounts during rollout. "
                f"The support team closed {account_count + 7} follow-up tickets by noon. "
                "Operators noted that the status page remained available for the full window."
            ),
            title=f"Migration update {index}",
        )
        items.append(_item(index, document))
    return items


class TestRecentHotspotBenchmarks:
    """Benchmarks for recently optimized code paths without external services."""

    def test_aggregation_sentence_cache_scan(self, benchmark, aggregation_items) -> None:
        """Measure the duplicate, contradiction, and fallback scan sharing one cache."""
        agent = _agent()
        source_weights = [agent._build_source_weight(item) for item in aggregation_items]

        def scan_with_shared_cache() -> tuple[int, int, int, int, int]:
            sentence_cache = _SentenceCache()
            duplicate_signals = agent._detect_duplicate_signals(
                aggregation_items,
                sentence_cache=sentence_cache,
            )
            contradiction_hints = agent._detect_contradiction_hints(
                aggregation_items,
                sentence_cache=sentence_cache,
            )
            fallback_claims = agent._fallback_claims(
                aggregation_items,
                source_weights,
                sentence_cache=sentence_cache,
            )
            return (
                len(duplicate_signals),
                len(contradiction_hints),
                len(fallback_claims),
                len(sentence_cache._documents),
                len(sentence_cache._blocks),
            )

        duplicate_count, contradiction_count, claim_count, document_cache_size, block_cache_size = (
            benchmark(scan_with_shared_cache)
        )

        assert duplicate_count >= 1
        assert contradiction_count >= 1
        assert claim_count == 5
        assert document_cache_size == len(aggregation_items)
        assert block_cache_size == len(aggregation_items)

        mean_ms = benchmark.stats.stats.mean * 1000
        assert mean_ms < 100.0, f"Aggregation heuristic scan too slow: {mean_ms:.2f}ms"

    def test_vector_point_id_generation_batch(self, benchmark) -> None:
        """Measure deterministic UUID generation used by Qdrant writers."""
        rows = [(request_id, request_id * 7) for request_id in range(1, 1001)]

        def generate_ids() -> list[str]:
            point_ids: list[str] = []
            for request_id, entity_id in rows:
                point_ids.append(summary_point_id(request_id, entity_id))
                point_ids.append(repository_point_id("test", "default", entity_id))
                point_ids.append(str_to_uuid(f"custom:{request_id}:{entity_id}"))
            return point_ids

        point_ids = benchmark(generate_ids)

        assert len(point_ids) == len(rows) * 3
        assert len(set(point_ids)) == len(point_ids)

        mean = benchmark.stats.stats.mean
        ops_per_sec = (len(point_ids) / mean) if mean > 0 else 0
        assert ops_per_sec > 3000, f"Point ID generation too slow: {ops_per_sec:.0f} ops/sec"
