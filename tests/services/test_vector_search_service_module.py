from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest

from app.services.vector_search_service import VectorSearchResult, VectorSearchService


@dataclass
class _DummyEmbeddingService:
    """Simple embedding service stub for unit tests."""

    async def generate_embedding(
        self, _text: str, *, language: str | None = None, task_type: str | None = None
    ) -> list[float]:
        if language:
            return [1.0, 0.0]
        return [1.0, 0.0]

    def deserialize_embedding(self, blob: bytes | str) -> list[float]:
        if blob == "bad":
            msg = "invalid embedding payload"
            raise ValueError(msg)
        return [1.0, 0.0]


class _DummyTopicRepo:
    def __init__(self, ids: list[int]) -> None:
        self._ids = ids

    async def async_search_request_ids(self, _query: str, *, candidate_limit: int) -> list[int]:
        assert candidate_limit > 0
        return list(self._ids)


class _DummyEmbeddingRepo:
    def __init__(
        self, rows_by_ids: list[dict[str, Any]], rows_recent: list[dict[str, Any]]
    ) -> None:
        self._rows_by_ids = rows_by_ids
        self._rows_recent = rows_recent

    async def async_get_embeddings_by_request_ids(
        self, _request_ids: list[int]
    ) -> list[dict[str, Any]]:
        return list(self._rows_by_ids)

    async def async_get_recent_embeddings(self, *, limit: int) -> list[dict[str, Any]]:
        assert limit > 0
        return list(self._rows_recent)


def _build_service() -> VectorSearchService:
    return VectorSearchService(
        db=object(),
        embedding_service=cast("Any", _DummyEmbeddingService()),
        max_results=5,
        min_similarity=0.3,
        candidate_multiplier=10,
        fallback_scan_limit=50,
    )


def test_init_validates_constructor_arguments() -> None:
    with pytest.raises(ValueError, match="max_results must be positive"):
        VectorSearchService(
            db=object(),
            embedding_service=cast("Any", _DummyEmbeddingService()),
            max_results=0,
        )
    with pytest.raises(ValueError, match=r"min_similarity must be between 0\.0 and 1\.0"):
        VectorSearchService(
            db=object(),
            embedding_service=cast("Any", _DummyEmbeddingService()),
            min_similarity=1.5,
        )
    with pytest.raises(ValueError, match="candidate_multiplier must be positive"):
        VectorSearchService(
            db=object(),
            embedding_service=cast("Any", _DummyEmbeddingService()),
            candidate_multiplier=0,
        )
    with pytest.raises(ValueError, match="fallback_scan_limit must be positive"):
        VectorSearchService(
            db=object(),
            embedding_service=cast("Any", _DummyEmbeddingService()),
            fallback_scan_limit=0,
        )


def test_materialize_candidates_skips_invalid_rows() -> None:
    service = _build_service()
    rows = [
        {
            "request_id": 1,
            "summary_id": 10,
            "embedding_blob": b"ok",
            "json_payload": {"summary_250": "text", "metadata": {"domain": "example.com"}},
            "normalized_url": "https://example.com/a",
            "input_url": "https://example.com/a",
        },
        {
            "request_id": 2,
            "summary_id": 11,
            "embedding_blob": "bad",
            "json_payload": {},
            "normalized_url": "https://example.com/b",
            "input_url": "https://example.com/b",
        },
    ]

    results = service._materialize_candidates(rows)
    assert len(results) == 1
    assert results[0]["request_id"] == 1
    assert results[0]["summary_id"] == 10
    assert results[0]["source"] == "example.com"


@pytest.mark.asyncio
async def test_search_returns_empty_for_blank_query() -> None:
    service = _build_service()
    assert await service.search("   ") == []


@pytest.mark.asyncio
async def test_search_prefers_scoped_candidates_and_applies_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service()
    service._topic_repo = cast("Any", _DummyTopicRepo([101, 102]))
    service._repo = cast(
        "Any",
        _DummyEmbeddingRepo(
            rows_by_ids=[
                {
                    "request_id": 101,
                    "summary_id": 201,
                    "embedding_blob": b"blob",
                    "json_payload": {
                        "summary_250": "alpha",
                        "metadata": {"domain": "keep.example", "published_at": "2026-01-01"},
                    },
                    "normalized_url": "https://keep.example/a",
                    "input_url": "https://keep.example/a",
                }
            ],
            rows_recent=[],
        ),
    )

    monkeypatch.setattr(
        service,
        "_compute_similarities",
        lambda _query_embedding, _candidates: [
            VectorSearchResult(
                request_id=101,
                summary_id=201,
                similarity_score=0.91,
                url="https://keep.example/a",
                title="Kept",
                snippet="alpha",
                source="keep.example",
                published_at="2026-01-01",
            ),
            VectorSearchResult(
                request_id=102,
                summary_id=202,
                similarity_score=0.92,
                url="https://drop.example/a",
                title="Dropped",
                snippet="beta",
                source="drop.example",
                published_at="2026-01-01",
            ),
        ],
    )

    class _Filters:
        def has_filters(self) -> bool:
            return True

        def matches(self, result: VectorSearchResult) -> bool:
            return result.source == "keep.example"

    filtered = await service.search("semantic query", filters=cast("Any", _Filters()))
    assert len(filtered) == 1
    assert filtered[0].source == "keep.example"
