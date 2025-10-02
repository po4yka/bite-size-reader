from __future__ import annotations

from typing import cast

import pytest

from app.adapters.external.firecrawl_parser import (
    FirecrawlClient,
    FirecrawlSearchItem,
    FirecrawlSearchResult,
)
from app.db.database import Database
from app.services.topic_search import LocalTopicSearchService, TopicSearchService


class DummyFirecrawl:
    def __init__(self, result: FirecrawlSearchResult) -> None:
        self.result = result
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, *, limit: int = 5) -> FirecrawlSearchResult:
        self.calls.append((query, limit))
        return self.result


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
    service = TopicSearchService(cast(FirecrawlClient, dummy), max_results=2)

    articles = await service.find_articles("Android System Design", correlation_id="cid-42")

    assert dummy.calls == [("Android System Design", 2)]
    assert len(articles) == 2
    assert articles[0].url == "https://example.com/android-architecture"
    assert articles[0].snippet is not None and articles[0].snippet.endswith("...")
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
    service = TopicSearchService(cast(FirecrawlClient, dummy), max_results=3)

    with pytest.raises(RuntimeError, match="quota exceeded"):
        await service.find_articles("Android System Design")


@pytest.mark.asyncio
async def test_local_search_returns_recent_matches(tmp_path) -> None:
    db_path = tmp_path / "app.db"
    database = Database(str(db_path))
    database.migrate()

    request_id = database.create_request(
        type_="url",
        status="completed",
        correlation_id="cid-1",
        chat_id=1,
        user_id=1,
        input_url="https://example.com/android",
        content_text="Android systems excel at modular design principles.",
    )
    database.insert_summary(
        request_id=request_id,
        lang="en",
        json_payload={
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

    other_request = database.create_request(
        type_="url",
        status="completed",
        correlation_id="cid-2",
        chat_id=1,
        user_id=1,
        input_url="https://example.com/cooking",
        content_text="All about pasta.",
    )
    database.insert_summary(
        request_id=other_request,
        lang="en",
        json_payload={
            "summary_250": "A deep dive into homemade pasta techniques.",
            "metadata": {
                "title": "Making Pasta",
                "canonical_url": "https://example.com/cooking",
                "domain": "example.com",
            },
        },
    )

    service = LocalTopicSearchService(db=database, max_results=2)

    results = await service.find_articles("Android System Design")

    assert len(results) == 1
    article = results[0]
    assert article.url == "https://example.com/android"
    assert article.title.startswith("Android System Design")
    assert article.source == "example.com"
    assert article.snippet is not None and "android" in article.snippet.lower()


@pytest.mark.asyncio
async def test_local_search_handles_empty_results(tmp_path) -> None:
    database = Database(str(tmp_path / "app.db"))
    database.migrate()

    service = LocalTopicSearchService(db=database, max_results=3)
    results = await service.find_articles("Nonexistent Topic")
    assert results == []


@pytest.mark.asyncio
async def test_local_search_rejects_blank_queries(tmp_path) -> None:
    database = Database(str(tmp_path / "app.db"))
    database.migrate()
    service = LocalTopicSearchService(db=database, max_results=2)

    with pytest.raises(ValueError):
        await service.find_articles("   ")


@pytest.mark.asyncio
async def test_local_search_index_finds_older_match(tmp_path) -> None:
    database = Database(str(tmp_path / "app.db"))
    database.migrate()

    matching_request = database.create_request(
        type_="url",
        status="completed",
        correlation_id="cid-3",
        chat_id=1,
        user_id=1,
        input_url="https://example.com/android-old",
        content_text="Legacy overview of Android modular design patterns.",
    )
    database.insert_summary(
        request_id=matching_request,
        lang="en",
        json_payload={
            "summary_250": "Android modular design enables reliable scaling.",
            "metadata": {
                "title": "Designing Android Systems",
                "canonical_url": "https://example.com/android-old",
                "domain": "example.com",
                "published_at": "2023-10-01",
            },
        },
    )

    # Insert a newer, non-matching summary so fallback scans would skip the older entry.
    newer_request = database.create_request(
        type_="url",
        status="completed",
        correlation_id="cid-4",
        chat_id=1,
        user_id=1,
        input_url="https://example.com/cooking-souffle",
        content_text="All about baking souffles.",
    )
    database.insert_summary(
        request_id=newer_request,
        lang="en",
        json_payload={
            "summary_250": "Souffles require gentle heat and timing.",
            "metadata": {
                "title": "Baking the Perfect Souffle",
                "canonical_url": "https://example.com/cooking-souffle",
                "domain": "example.com",
            },
        },
    )

    service = LocalTopicSearchService(db=database, max_results=1, max_scan=1)

    results = await service.find_articles("Android modular design")

    assert results
    assert results[0].url == "https://example.com/android-old"


def test_database_populates_topic_search_index(tmp_path) -> None:
    database = Database(str(tmp_path / "app.db"))
    database.migrate()

    request_id = database.create_request(
        type_="url",
        status="completed",
        correlation_id="cid-5",
        chat_id=1,
        user_id=1,
        input_url="https://example.com/ai",
        content_text="Artificial intelligence fundamentals.",
    )
    database.insert_summary(
        request_id=request_id,
        lang="en",
        json_payload={
            "summary_250": "AI systems rely on data and iterative training.",
            "metadata": {
                "title": "AI Fundamentals",
                "canonical_url": "https://example.com/ai",
                "domain": "example.com",
            },
        },
    )

    with database._database.connection_context():
        cursor = database._database.execute_sql(
            "SELECT url, title, body FROM topic_search_index LIMIT 1"
        )
        row = cursor.fetchone()

    assert row is not None
    assert "android" not in row[2]
    assert row[0] == "https://example.com/ai"
    assert "AI Fundamentals" in row[1]
