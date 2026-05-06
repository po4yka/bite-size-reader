from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete

from app.config.database import DatabaseConfig
from app.db.models import BatchSession, BatchSessionItem, Request, Summary, User
from app.db.session import Database
from app.infrastructure.persistence.sqlite.repositories.batch_session_repository import (
    SqliteBatchSessionRepositoryAdapter,
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
        await session.execute(delete(BatchSessionItem))
        await session.execute(delete(BatchSession))
        await session.execute(delete(Summary))
        await session.execute(delete(Request))
        await session.execute(delete(User))


async def _seed_user_requests_and_summaries(database: Database) -> tuple[int, list[int]]:
    async with database.transaction() as session:
        user = User(telegram_user_id=9301, username="batcher", is_owner=True)
        session.add(user)
        request_ids: list[int] = []
        for index in range(3):
            request = Request(
                type="url",
                status="completed",
                correlation_id=f"batch-request-{index}",
                user_id=user.telegram_user_id,
                input_url=f"https://example.com/{index}",
                normalized_url=f"https://example.com/{index}",
                dedupe_hash=f"batch-request-{index}",
            )
            session.add(request)
            await session.flush()
            request_ids.append(request.id)
            session.add(
                Summary(
                    request_id=request.id,
                    lang="en",
                    json_payload={"summary_250": f"summary {index}"},
                )
            )
        return user.telegram_user_id, request_ids


@pytest.mark.asyncio
async def test_batch_session_repository_crud_relationships_and_joined_read(
    database: Database,
) -> None:
    user_id, request_ids = await _seed_user_requests_and_summaries(database)
    repo = SqliteBatchSessionRepositoryAdapter(database)

    session_id = await repo.async_create_batch_session(
        user_id=user_id,
        correlation_id="test-batch-session-123",
        total_urls=3,
    )
    session = await repo.async_get_batch_session(session_id)
    assert session is not None
    assert session["user"] == user_id
    assert session["total_urls"] == 3
    assert session["status"] == "processing"
    assert (await repo.async_get_batch_session_by_correlation_id("test-batch-session-123"))[
        "id"
    ] == session_id

    item_ids = [
        await repo.async_add_batch_session_item(
            session_id=session_id,
            request_id=request_id,
            position=index,
        )
        for index, request_id in enumerate(request_ids)
    ]
    await repo.async_update_batch_session_item_series_info(
        item_ids[0],
        is_series_part=True,
        series_order=1,
        series_title="Series",
    )

    items = await repo.async_get_batch_session_items(session_id)
    assert [item["position"] for item in items] == [0, 1, 2]
    assert items[0]["batch_session"] == session_id
    assert items[0]["request"] == request_ids[0]
    assert items[0]["series_title"] == "Series"

    await repo.async_update_batch_session_counts(session_id, successful_count=3, failed_count=0)
    await repo.async_update_batch_session_relationship(
        session_id,
        relationship_type="series",
        relationship_confidence=0.95,
        relationship_metadata={"pattern": "Part N"},
    )
    await repo.async_update_batch_session_combined_summary(
        session_id,
        {"overview": "combined"},
    )
    await repo.async_update_batch_session_status(
        session_id,
        "completed",
        analysis_status="complete",
        processing_time_ms=1500,
    )

    updated_session = await repo.async_get_batch_session(session_id)
    assert updated_session is not None
    assert updated_session["successful_count"] == 3
    assert updated_session["relationship_type"] == "series"
    assert updated_session["relationship_confidence"] == 0.95
    assert updated_session["relationship_metadata_json"] == {"pattern": "Part N"}
    assert updated_session["combined_summary_json"] == {"overview": "combined"}
    assert updated_session["status"] == "completed"
    assert updated_session["analysis_status"] == "complete"
    assert updated_session["processing_time_ms"] == 1500

    session_with_summaries = await repo.async_get_batch_session_with_summaries(session_id)
    assert session_with_summaries is not None
    assert len(session_with_summaries["items"]) == 3
    assert session_with_summaries["items"][0]["request"]["id"] == request_ids[0]
    assert session_with_summaries["items"][0]["summary"]["json_payload"] == {
        "summary_250": "summary 0"
    }

    user_sessions = await repo.async_get_user_batch_sessions(user_id, status="completed")
    assert [row["id"] for row in user_sessions] == [session_id]

    assert await repo.async_delete_batch_session(session_id) is True
    assert await repo.async_get_batch_session(session_id) is None
    assert await repo.async_delete_batch_session(session_id) is False
