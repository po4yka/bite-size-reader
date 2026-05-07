from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import select

from app.adapters.external.firecrawl.models import FirecrawlSearchItem, FirecrawlSearchResult
from app.application.services.topic_search import LocalTopicSearchService, TopicSearchService
from app.db.models import TopicSearchIndex
from app.infrastructure.persistence.repositories.topic_search_repository import (
    TopicSearchRepositoryAdapter,
)
from tests.db_helpers_async import create_request, insert_summary

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.application.ports.search import TopicSearchResultPort
    from app.db.session import Database


class DummyFirecrawl:
    def __init__(self, result: FirecrawlSearchResult) -> None:
        self.result = result
        self.calls: list[tuple[str, int]] = []

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        request_id: int | None = None,
    ) -> TopicSearchResultPort:
        self.calls.append((query, limit))
        return cast("TopicSearchResultPort", self.result)


# ---------------------------------------------------------------------------
# Pure-Python tests: TopicSearchService over a fake firecrawl backend.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_articles_normalizes_and_limits() -> None:
    long_snippet = "This is a long snippet " * 30
    result = FirecrawlSearchResult(
        status="success",
        results=[
            FirecrawlSearchItem(
                title="Android Architecture Guide",
                url="https://example.com/android-architecture",
                snippet=long_snippet,
                source="Example News",
                published_at="2024-02-15",
            ),
            FirecrawlSearchItem(
                title="Scaling Android Services",
                url="https://example.com/android-services",
                snippet="Insights on scaling Android services across regions.",
                source=None,
                published_at=None,
            ),
            FirecrawlSearchItem(
                title="Duplicate Entry",
                url="https://example.com/android-architecture",
                snippet="Duplicate should be ignored.",
                source="Example News",
                published_at="2024-02-16",
            ),
        ],
        total_results=3,
    )

    dummy = DummyFirecrawl(result)
    service = TopicSearchService(dummy, max_results=2)

    articles = await service.find_articles("Android System Design", correlation_id="cid-42")

    assert dummy.calls == [("Android System Design", 2)]
    assert len(articles) == 2
    assert articles[0].url == "https://example.com/android-architecture"
    assert articles[0].snippet is not None
    assert articles[0].snippet.endswith("...")
    assert articles[1].url == "https://example.com/android-services"


@pytest.mark.asyncio
async def test_find_articles_raises_on_error_status() -> None:
    result = FirecrawlSearchResult(
        status="error",
        results=[],
        error_text="quota exceeded",
        http_status=429,
    )

    dummy = DummyFirecrawl(result)
    service = TopicSearchService(dummy, max_results=3)

    with pytest.raises(RuntimeError, match="quota exceeded"):
        await service.find_articles("Android System Design")


# ---------------------------------------------------------------------------
# DB-backed tests: LocalTopicSearchService against the SQLAlchemy repository.
# ---------------------------------------------------------------------------


async def _index_summary(
    session: AsyncSession,
    repo: TopicSearchRepositoryAdapter,
    *,
    correlation_id: str,
    input_url: str,
    content_text: str,
    summary_payload: dict,
) -> int:
    request_id = await create_request(
        session,
        type_="url",
        status="completed",
        correlation_id=correlation_id,
        chat_id=1,
        user_id=1,
        input_url=input_url,
        normalized_url=input_url,
        content_text=content_text,
    )
    await insert_summary(
        session, request_id=request_id, lang="en", json_payload=summary_payload
    )
    await session.commit()
    await repo.async_refresh_index(request_id)
    return request_id


async def test_local_search_returns_recent_matches(
    session: AsyncSession, database: Database
) -> None:
    repo = TopicSearchRepositoryAdapter(database)

    await _index_summary(
        session,
        repo,
        correlation_id="cid-1",
        input_url="https://example.com/android",
        content_text="Android systems excel at modular design principles.",
        summary_payload={
            "summary_250": "Android system design focuses on scalable services.",
            "topic_tags": ["Android", "Architecture"],
            "metadata": {
                "title": "Android System Design 101",
                "canonical_url": "https://example.com/android",
                "domain": "example.com",
                "published_at": "2024-01-01",
            },
        },
    )
    await _index_summary(
        session,
        repo,
        correlation_id="cid-2",
        input_url="https://example.com/cooking",
        content_text="All about pasta.",
        summary_payload={
            "summary_250": "A deep dive into homemade pasta techniques.",
            "metadata": {
                "title": "Making Pasta",
                "canonical_url": "https://example.com/cooking",
                "domain": "example.com",
            },
        },
    )

    service = LocalTopicSearchService(repo, max_results=2)

    results = await service.find_articles("Android System Design")

    assert len(results) == 1
    article = results[0]
    assert article.url == "https://example.com/android"
    assert article.title.startswith("Android System Design")
    assert article.source == "example.com"
    assert article.snippet is not None
    assert "android" in article.snippet.lower()


async def test_local_search_handles_empty_results(database: Database) -> None:
    service = LocalTopicSearchService(TopicSearchRepositoryAdapter(database), max_results=3)
    results = await service.find_articles("Nonexistent Topic")
    assert results == []


async def test_local_search_rejects_blank_queries(database: Database) -> None:
    service = LocalTopicSearchService(TopicSearchRepositoryAdapter(database), max_results=2)

    with pytest.raises(ValueError):
        await service.find_articles("   ")


async def test_local_search_index_finds_older_match(
    session: AsyncSession, database: Database
) -> None:
    repo = TopicSearchRepositoryAdapter(database)

    await _index_summary(
        session,
        repo,
        correlation_id="cid-3",
        input_url="https://example.com/android-old",
        content_text="Legacy overview of Android modular design patterns.",
        summary_payload={
            "summary_250": "Android modular design enables reliable scaling.",
            "metadata": {
                "title": "Designing Android Systems",
                "canonical_url": "https://example.com/android-old",
                "domain": "example.com",
                "published_at": "2023-10-01",
            },
        },
    )

    # Insert a newer, non-matching summary so a naive recent-first scan would skip the match.
    await _index_summary(
        session,
        repo,
        correlation_id="cid-4",
        input_url="https://example.com/cooking-souffle",
        content_text="All about baking souffles.",
        summary_payload={
            "summary_250": "Souffles require gentle heat and timing.",
            "metadata": {
                "title": "Baking the Perfect Souffle",
                "canonical_url": "https://example.com/cooking-souffle",
                "domain": "example.com",
            },
        },
    )

    service = LocalTopicSearchService(repo, max_results=1, max_scan=1)

    results = await service.find_articles("Android modular design")

    assert results
    assert results[0].url == "https://example.com/android-old"


async def test_topic_search_index_is_populated_on_refresh(
    session: AsyncSession, database: Database
) -> None:
    repo = TopicSearchRepositoryAdapter(database)

    request_id = await _index_summary(
        session,
        repo,
        correlation_id="cid-5",
        input_url="https://example.com/ai",
        content_text="Artificial intelligence fundamentals.",
        summary_payload={
            "summary_250": "AI systems rely on data and iterative training.",
            "metadata": {
                "title": "AI Fundamentals",
                "canonical_url": "https://example.com/ai",
                "domain": "example.com",
            },
        },
    )

    indexed = await session.scalar(
        select(TopicSearchIndex).where(TopicSearchIndex.request_id == request_id)
    )
    assert indexed is not None
    assert indexed.url == "https://example.com/ai"
    assert "AI Fundamentals" in (indexed.title or "")
    assert "android" not in (indexed.body or "").lower()
