"""Tests for Chroma-backed signal topic similarity."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.application.services.signal_scoring import SignalCandidate
from app.infrastructure.search.chroma_topic_similarity import ChromaTopicSimilarityAdapter


class _FakeVectorStore:
    def __init__(self, *, available: bool = True, raw: dict | None = None) -> None:
        self.available = available
        self.raw = raw or {"distances": [[0.2, 0.7]], "metadatas": [[{}, {}]]}
        self.queries: list[tuple[list[float], dict, int]] = []

    def health_check(self) -> bool:
        return self.available

    def query(self, query_vector, filters, top_k):
        self.queries.append((list(query_vector), dict(filters or {}), top_k))
        return self.raw


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
        def query(self, query_vector, filters, top_k):
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
