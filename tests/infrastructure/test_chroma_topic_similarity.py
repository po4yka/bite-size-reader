"""Tests for Chroma-backed signal topic similarity."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

from app.application.services.signal_scoring import SignalCandidate
from app.infrastructure.search.chroma_topic_similarity import ChromaTopicSimilarityAdapter
from app.infrastructure.vector.result_types import VectorQueryHit, VectorQueryResult

if TYPE_CHECKING:
    from collections.abc import Sequence


def _make_result(distances: list[float]) -> VectorQueryResult:
    return VectorQueryResult(
        hits=[VectorQueryHit(id=str(i), distance=d, metadata={}) for i, d in enumerate(distances)]
    )


class _FakeVectorStore:
    def __init__(self, *, available: bool = True, result: VectorQueryResult | None = None) -> None:
        self.available = available
        self.result = result if result is not None else _make_result([0.2, 0.7])
        self.queries: list[tuple[list[float], dict, int]] = []

    def health_check(self) -> bool:
        return self.available

    def query(
        self,
        query_vector: Sequence[float],
        filters: dict[str, Any] | None,
        top_k: int,
    ) -> VectorQueryResult:
        self.queries.append((list(query_vector), dict(filters or {}), top_k))
        return self.result


@pytest.mark.asyncio
async def test_chroma_topic_similarity_queries_candidate_text() -> None:
    store = _FakeVectorStore()
    embedding = SimpleNamespace(generate_embedding=AsyncMock(return_value=[0.1, 0.2, 0.3]))
    adapter = ChromaTopicSimilarityAdapter(
        vector_store=store,
        embedding_service=embedding,
        user_id=1001,
    )

    score = await adapter.score_item(
        SignalCandidate(
            feed_item_id=1,
            source_id=1,
            source_kind="rss",
            title="Useful Python post",
            canonical_url="https://example.com/post",
            metadata={"content_text": "Detailed content"},
        )
    )

    assert score == pytest.approx(0.8)
    embedding.generate_embedding.assert_awaited_once()
    assert store.queries[0][1] == {"user_id": 1001}
    assert store.queries[0][2] == 8


@pytest.mark.asyncio
async def test_chroma_topic_similarity_returns_zero_when_query_fails() -> None:
    class BrokenStore(_FakeVectorStore):
        def query(
            self,
            query_vector: Sequence[float],
            filters: dict[str, Any] | None,
            top_k: int,
        ) -> VectorQueryResult:
            raise RuntimeError("chroma down")

    embedding = SimpleNamespace(generate_embedding=AsyncMock(return_value=[0.1]))
    adapter = ChromaTopicSimilarityAdapter(
        vector_store=BrokenStore(),
        embedding_service=embedding,
        user_id=None,
    )

    assert await adapter.score_item(SignalCandidate(1, 1, "rss", title="x")) == 0.0


def test_chroma_topic_similarity_readiness_uses_health_check() -> None:
    adapter = ChromaTopicSimilarityAdapter(
        vector_store=_FakeVectorStore(available=False),
        embedding_service=SimpleNamespace(generate_embedding=AsyncMock(return_value=[0.1])),
    )

    assert adapter.is_ready() is False
