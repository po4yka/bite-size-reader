from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, select

from app.application.services.topic_search_utils import TopicSearchDocument
from app.config.database import DatabaseConfig
from app.db.models import Request, Summary, SummaryTag, Tag, TopicSearchIndex, User
from app.db.session import Database
from app.infrastructure.persistence.repositories.topic_search_repository import (
    TopicSearchRepositoryAdapter,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def _test_dsn() -> str:
    return os.getenv("TEST_DATABASE_URL", "")


@pytest.fixture
async def database() -> AsyncGenerator[Database]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for Postgres repository tests")

    db = Database(DatabaseConfig(dsn=dsn, pool_size=1, max_overflow=1))
    await db.migrate()
    await _clear(db)
    try:
        yield db
    finally:
        await _clear(db)
        await db.dispose()


async def _clear(database: Database) -> None:
    async with database.transaction() as session:
        await session.execute(delete(TopicSearchIndex))
        await session.execute(delete(SummaryTag))
        await session.execute(delete(Tag))
        await session.execute(delete(Summary))
        await session.execute(delete(Request))
        await session.execute(delete(User))


async def _create_summary(
    database: Database,
    *,
    user_id: int,
    suffix: str,
    title: str,
    summary_text: str,
    content_text: str,
) -> tuple[Request, Summary]:
    async with database.transaction() as session:
        user = await session.get(User, user_id)
        if user is None:
            user = User(telegram_user_id=user_id, username=f"user-{user_id}")
            session.add(user)
            await session.flush()
        request = Request(
            user_id=user_id,
            type="url",
            status="completed",
            input_url=f"https://example.com/{suffix}",
            normalized_url=f"https://example.com/{suffix}",
            dedupe_hash=f"topic-hash-{suffix}",
            content_text=content_text,
        )
        session.add(request)
        await session.flush()
        summary = Summary(
            request_id=request.id,
            lang="en",
            json_payload={
                "title": title,
                "summary_250": summary_text,
                "tldr": summary_text,
                "topic_tags": ["postgres", "search"],
                "metadata": {
                    "domain": "example.com",
                    "canonical_url": f"https://example.com/{suffix}",
                    "published_at": "2026-05-06",
                },
            },
        )
        session.add(summary)
        await session.flush()
        return request, summary


@pytest.mark.asyncio
async def test_topic_search_repository_indexes_searches_and_paginates(
    database: Database,
) -> None:
    repo = TopicSearchRepositoryAdapter(database)
    owner_request, _ = await _create_summary(
        database,
        user_id=8301,
        suffix="postgres",
        title="Postgres Search",
        summary_text="Async SQLAlchemy powers topic discovery",
        content_text="PostgreSQL full text search for AI summaries",
    )
    other_request, _ = await _create_summary(
        database,
        user_id=8302,
        suffix="python",
        title="Python Search",
        summary_text="Python search pipelines use ranking",
        content_text="Python retrieval search",
    )

    await repo.async_rebuild_index()

    request_ids = await repo.async_search_request_ids("SQLAlchemy", candidate_limit=5)
    assert request_ids == [owner_request.id]

    results, total = await repo.async_fts_search_paginated("search", limit=10, offset=0)
    assert total == 2
    assert {row["request_id"] for row in results} == {owner_request.id, other_request.id}

    scoped, scoped_total = await repo.async_fts_search_paginated(
        "search",
        limit=10,
        offset=0,
        user_id=8301,
    )
    assert scoped_total == 1
    assert [row["request_id"] for row in scoped] == [owner_request.id]

    docs = await repo.async_search_documents("SQLAlchemy", limit=2)
    assert [doc.request_id for doc in docs] == [owner_request.id]
    assert docs[0].url == "https://example.com/postgres"


@pytest.mark.asyncio
async def test_topic_search_repository_writes_refreshes_and_merges_tags(
    database: Database,
) -> None:
    repo = TopicSearchRepositoryAdapter(database)
    request, summary = await _create_summary(
        database,
        user_id=8401,
        suffix="manual",
        title="Manual Index",
        summary_text="Initial text",
        content_text="initial body",
    )

    await repo.async_write_document(
        TopicSearchDocument(
            request_id=request.id,
            url="https://example.com/manual",
            title="Manual",
            snippet="Snippet",
            source="example.com",
            published_at="2026-05-06",
            body="manual search body",
            tags_text="manual",
        )
    )
    written_ids = await repo.async_search_request_ids("manual", candidate_limit=5)
    assert written_ids == [request.id]

    await repo.async_refresh_index(request.id)
    refreshed = await repo.async_search_documents("initial", limit=1)
    assert [doc.request_id for doc in refreshed] == [request.id]

    async with database.transaction() as session:
        tag = Tag(user_id=8401, name="Deep Learning", normalized_name="deep-learning")
        session.add(tag)
        await session.flush()
        session.add(SummaryTag(summary_id=summary.id, tag_id=tag.id, source="manual"))

    await repo.async_update_tags_for_summary(summary.id)
    async with database.session() as session:
        indexed = await session.scalar(
            select(TopicSearchIndex).where(TopicSearchIndex.request_id == request.id)
        )
    assert indexed is not None
    assert indexed.tags == "postgres search Deep Learning"


@pytest.mark.asyncio
async def test_topic_search_repository_scan_fallback(database: Database) -> None:
    repo = TopicSearchRepositoryAdapter(database)
    request, _ = await _create_summary(
        database,
        user_id=8501,
        suffix="fallback",
        title="Fallback Match",
        summary_text="Fallback search can scan stored summaries",
        content_text="needle appears in stored content",
    )

    docs = await repo.async_scan_documents(
        terms=["needle"],
        normalized_query="needle",
        seen_urls=set(),
        limit=3,
        max_scan=10,
    )

    assert [doc.request_id for doc in docs] == [request.id]
    assert docs[0].title == "Fallback Match"
