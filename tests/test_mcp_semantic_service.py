from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import pytest

from app.mcp.article_service import ArticleReadService
from app.mcp.context import McpServerContext
from app.mcp.http_auth import McpRequestIdentity
from app.mcp.semantic_service import SemanticSearchService
from tests.mcp_test_utils import insert_scoped_summary

pytest_plugins = ("tests.mcp_test_support",)

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager


class FakeVectorResult:
    def __init__(
        self,
        *,
        request_id: int,
        summary_id: int,
        similarity_score: float,
        snippet: str,
        chunk_id: str | None = None,
        window_id: str | None = None,
    ) -> None:
        self.request_id = request_id
        self.summary_id = summary_id
        self.similarity_score = similarity_score
        self.url = f"https://example.com/{summary_id}"
        self.title = f"title-{summary_id}"
        self.snippet = snippet
        self.text = snippet
        self.source = "example.com"
        self.published_at = None
        self.window_id = window_id
        self.window_index = None
        self.chunk_id = chunk_id
        self.section = "body"
        self.topics = ["#topic"]
        self.local_keywords = ["keyword"]
        self.semantic_boosters: list[str] = []
        self.local_summary = snippet


class FakeVectorSearchPayload:
    def __init__(self, results: list[FakeVectorResult], has_more: bool = False) -> None:
        self.results = results
        self.has_more = has_more


class FakeVectorService:
    def __init__(self, results: list[FakeVectorResult]) -> None:
        self._results = results

    async def search(self, *_args: Any, **_kwargs: Any) -> FakeVectorSearchPayload:
        return FakeVectorSearchPayload(self._results, has_more=False)


@pytest.mark.asyncio
async def test_semantic_search_groups_chunks_and_min_similarity(
    mcp_test_db: DatabaseSessionManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    sid1, req1 = insert_scoped_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/one",
        title="One",
        tags=["#ai"],
        created_at=now,
    )
    sid2, req2 = insert_scoped_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/two",
        title="Two",
        tags=["#ai"],
        created_at=now.replace(hour=11),
    )

    context = McpServerContext(user_id=1)
    service = SemanticSearchService(context, ArticleReadService(context))
    fake_results = [
        FakeVectorResult(
            request_id=req1,
            summary_id=sid1,
            similarity_score=0.91,
            snippet="chunk-1",
            chunk_id="chunk-a",
            window_id="w-a",
        ),
        FakeVectorResult(
            request_id=req1,
            summary_id=sid1,
            similarity_score=0.83,
            snippet="chunk-2",
            chunk_id="chunk-b",
            window_id="w-b",
        ),
        FakeVectorResult(
            request_id=req2,
            summary_id=sid2,
            similarity_score=0.61,
            snippet="low-sim",
            chunk_id="chunk-c",
            window_id="w-c",
        ),
    ]

    async def fake_vector() -> FakeVectorService:
        return FakeVectorService(fake_results)

    monkeypatch.setattr(context, "init_vector_service", fake_vector)

    payload = await service.semantic_search(
        "ai policy",
        limit=10,
        min_similarity=0.7,
        include_chunks=True,
    )
    results = payload["results"]

    assert payload["search_backend"] == "vector"
    assert len(results) == 1
    assert results[0]["summary_id"] == sid1
    assert results[0]["similarity_score"] == pytest.approx(0.91)
    assert results[0]["semantic_match_count"] == 2
    assert len(results[0]["semantic_matches"]) == 2


@pytest.mark.asyncio
async def test_semantic_search_keyword_fallback_when_semantic_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = McpServerContext()
    article_service = ArticleReadService(context)
    service = SemanticSearchService(context, article_service)

    async def no_vector() -> None:
        return None

    async def no_local(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    async def keyword_search(query: str, limit: int = 10) -> dict[str, Any]:
        return {
            "results": [{"summary_id": 101, "title": "keyword result"}],
            "total": 1,
            "query": query,
        }

    monkeypatch.setattr(context, "init_vector_service", no_vector)
    monkeypatch.setattr(service, "_search_local_vectors", no_local)
    monkeypatch.setattr(article_service, "search_articles", keyword_search)

    payload = await service.semantic_search("topic", limit=5)
    assert payload["search_type"] == "keyword_fallback"
    assert payload["search_backend"] == "fts"
    assert payload["results"][0]["summary_id"] == 101


@pytest.mark.asyncio
async def test_find_similar_articles_excludes_source_summary(
    mcp_test_db: DatabaseSessionManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    sid1, req1 = insert_scoped_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/seed",
        title="Seed",
        tags=["#ai"],
        created_at=now,
    )
    sid2, req2 = insert_scoped_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/other",
        title="Other",
        tags=["#ai"],
        created_at=now.replace(hour=11),
    )

    context = McpServerContext(user_id=1)
    service = SemanticSearchService(context, ArticleReadService(context))
    fake_results = [
        FakeVectorResult(
            request_id=req1,
            summary_id=sid1,
            similarity_score=0.95,
            snippet="seed match",
            chunk_id="chunk-seed",
            window_id="w-seed",
        ),
        FakeVectorResult(
            request_id=req2,
            summary_id=sid2,
            similarity_score=0.88,
            snippet="other match",
            chunk_id="chunk-other",
            window_id="w-other",
        ),
    ]

    async def fake_vector() -> FakeVectorService:
        return FakeVectorService(fake_results)

    monkeypatch.setattr(context, "init_vector_service", fake_vector)

    payload = await service.find_similar_articles(summary_id=sid1, limit=10)
    result_ids = [row["summary_id"] for row in payload["results"]]

    assert sid1 not in result_ids


@pytest.mark.asyncio
async def test_semantic_search_uses_request_scoped_identity(
    mcp_test_db: DatabaseSessionManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    sid1, req1 = insert_scoped_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/user1",
        title="User1",
        tags=["#ai"],
        created_at=now,
    )
    sid2, req2 = insert_scoped_summary(
        db=mcp_test_db,
        user_id=2,
        url="https://example.com/user2",
        title="User2",
        tags=["#ai"],
        created_at=now.replace(hour=11),
    )

    context = McpServerContext(user_id=9999)
    service = SemanticSearchService(context, ArticleReadService(context))
    fake_results = [
        FakeVectorResult(
            request_id=req1,
            summary_id=sid1,
            similarity_score=0.92,
            snippet="user1 chunk",
            chunk_id="chunk-user1",
            window_id="w-user1",
        ),
        FakeVectorResult(
            request_id=req2,
            summary_id=sid2,
            similarity_score=0.87,
            snippet="user2 chunk",
            chunk_id="chunk-user2",
            window_id="w-user2",
        ),
    ]

    async def fake_vector() -> FakeVectorService:
        return FakeVectorService(fake_results)

    monkeypatch.setattr(context, "init_vector_service", fake_vector)

    with context.request_identity_scope(
        McpRequestIdentity(
            user_id=1,
            client_id="mcp-public-v1",
            username="semantic-user",
            auth_source="authorization",
        )
    ):
        payload = await service.semantic_search(
            "ai policy",
            limit=10,
            min_similarity=0.7,
            include_chunks=True,
        )

    results = payload["results"]
    assert len(results) == 1
    assert results[0]["summary_id"] == sid1


@pytest.mark.asyncio
async def test_vector_sync_gap_reports_missing_and_extra(
    mcp_test_db: DatabaseSessionManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    sid1, _ = insert_scoped_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/sync-a",
        title="Sync A",
        tags=["#sync"],
        created_at=now,
    )
    sid2, _ = insert_scoped_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/sync-b",
        title="Sync B",
        tags=["#sync"],
        created_at=now.replace(hour=11),
    )

    class FakeStore:
        def get_indexed_summary_ids(
            self,
            *,
            user_id: int | None = None,
            limit: int | None = 5000,
        ) -> set[int]:
            _ = (user_id, limit)
            return {sid2, 99999}

    class FakeVector:
        _vector_store = FakeStore()

    async def fake_vector() -> FakeVector:
        return FakeVector()

    context = McpServerContext(user_id=1)
    service = SemanticSearchService(context, ArticleReadService(context))
    monkeypatch.setattr(context, "init_vector_service", fake_vector)

    payload = await service.vector_sync_gap(max_scan=1000, sample_size=10)
    assert payload["missing_in_vector_count"] == 1
    assert sid1 in payload["missing_in_vector_sample"]
    assert payload["missing_in_sqlite_count"] == 1
    assert 99999 in payload["missing_in_sqlite_sample"]
