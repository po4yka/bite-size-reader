from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete

from app.application.dto.aggregation import AggregationFailure, NormalizedSourceDocument
from app.config.database import DatabaseConfig
from app.db.models import AggregationSession, AggregationSessionItem, Request, User
from app.db.session import Database
from app.domain.models.request import RequestStatus
from app.domain.models.source import (
    AggregationItemStatus,
    AggregationSessionStatus,
    SourceItem,
    SourceKind,
)
from app.infrastructure.persistence.repositories.aggregation_session_repository import (
    SqliteAggregationSessionRepositoryAdapter,
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
        await session.execute(delete(AggregationSessionItem))
        await session.execute(delete(AggregationSession))
        await session.execute(delete(Request))
        await session.execute(delete(User))


async def _seed_user_and_request(database: Database) -> tuple[int, int]:
    async with database.transaction() as session:
        user = User(telegram_user_id=9201, username="aggregator", is_owner=True)
        request = Request(
            type="url",
            status=RequestStatus.PENDING.value,
            correlation_id="agg-item-req",
            user_id=user.telegram_user_id,
            input_url="https://example.com/a",
            normalized_url="https://example.com/a",
            dedupe_hash="agg-req-hash",
        )
        session.add_all([user, request])
        await session.flush()
        return user.telegram_user_id, request.id


@pytest.mark.asyncio
async def test_aggregation_session_repository_persists_items_and_lifecycle(
    database: Database,
) -> None:
    user_id, request_id = await _seed_user_and_request(database)
    repo = SqliteAggregationSessionRepositoryAdapter(database)

    session_id = await repo.async_create_aggregation_session(
        user_id=user_id,
        correlation_id="agg-session-1",
        total_items=3,
        bundle_metadata={"submitted_via": "test"},
    )
    assert (await repo.async_get_aggregation_session_by_correlation_id("agg-session-1"))[
        "id"
    ] == session_id
    assert await repo.async_count_user_aggregation_sessions(user_id) == 1
    assert len(await repo.async_get_user_aggregation_sessions(user_id)) == 1

    await repo.async_update_aggregation_session_status(
        session_id,
        status=AggregationSessionStatus.PROCESSING,
    )
    first = SourceItem.create(
        kind=SourceKind.WEB_ARTICLE,
        original_value="https://example.com/a?utm_source=test",
    )
    second = SourceItem.create(
        kind=SourceKind.YOUTUBE_VIDEO,
        original_value="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        external_id="dQw4w9WgXcQ",
    )
    duplicate = SourceItem.create(
        kind=SourceKind.WEB_ARTICLE, original_value="https://example.com/a"
    )

    first_item_id = await repo.async_add_aggregation_session_item(session_id, first, 0)
    second_item_id = await repo.async_add_aggregation_session_item(session_id, second, 1)
    duplicate_item_id = await repo.async_add_aggregation_session_item(session_id, duplicate, 2)

    items = await repo.async_get_aggregation_session_items(session_id)
    assert [item["position"] for item in items] == [0, 1, 2]
    assert items[0]["status"] == AggregationItemStatus.PENDING.value
    assert items[2]["status"] == AggregationItemStatus.DUPLICATE.value
    assert items[2]["duplicate_of_item_id"] == first_item_id
    assert duplicate_item_id == items[2]["id"]

    first_document = NormalizedSourceDocument.from_extracted_content(
        source_item=first,
        text="Article body",
        title="Example",
        detected_language="en",
        content_source="markdown",
        metadata={"source": "firecrawl"},
    )
    await repo.async_update_aggregation_session_item_result(
        first_item_id,
        status=AggregationItemStatus.EXTRACTED,
        request_id=request_id,
        normalized_document=first_document,
        extraction_metadata={"latency_ms": 42},
    )
    await repo.async_update_aggregation_session_item_result(
        second_item_id,
        status=AggregationItemStatus.FAILED,
        failure=AggregationFailure(
            code="extract_timeout",
            message="Video transcript timed out",
            retryable=True,
            details={"timeout_s": 30},
        ),
    )
    await repo.async_update_aggregation_session_counts(
        session_id,
        successful_count=1,
        failed_count=1,
        duplicate_count=1,
    )
    await repo.async_update_aggregation_session_output(
        session_id,
        {
            "source_type": "mixed",
            "overview": "Bundle synthesis output",
            "used_source_count": 1,
        },
    )
    await repo.async_update_aggregation_session_status(
        session_id,
        status=AggregationSessionStatus.PARTIAL,
        processing_time_ms=1234,
    )

    session = await repo.async_get_aggregation_session(session_id)
    assert session is not None
    assert session["user"] == user_id
    assert session["duplicate_count"] == 1
    assert session["failed_count"] == 1
    assert session["progress_percent"] == 100
    assert session["status"] == AggregationSessionStatus.PARTIAL.value
    assert session["bundle_metadata_json"] == {"submitted_via": "test"}
    assert session["started_at"] is not None
    assert session["completed_at"] is not None
    assert session["aggregation_output_json"]["source_type"] == "mixed"

    updated_items = await repo.async_get_aggregation_session_items(session_id)
    assert updated_items[0]["request"] == request_id
    assert updated_items[0]["request_id"] == request_id
    assert updated_items[0]["normalized_document_json"]["title"] == "Example"
    assert updated_items[1]["failure_code"] == "extract_timeout"
    assert updated_items[1]["failure_details_json"]["timeout_s"] == 30
