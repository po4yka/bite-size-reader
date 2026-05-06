from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, func, select

from app.config.database import DatabaseConfig
from app.db.batch_operations import BatchOperations
from app.db.models import LLMCall, Request, Summary, User
from app.db.session import Database

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def _test_dsn() -> str:
    return os.getenv("TEST_DATABASE_URL", "")


@pytest.fixture
async def database() -> AsyncGenerator[Database]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for Postgres batch operation tests")

    db = Database(DatabaseConfig(dsn=dsn, pool_size=1, max_overflow=1))
    await db.migrate()
    await _clear(db)
    try:
        yield db
    finally:
        await _clear(db)
        await db.dispose()


async def _clear(db: Database) -> None:
    async with db.transaction() as session:
        await session.execute(delete(Summary))
        await session.execute(delete(LLMCall))
        await session.execute(delete(Request))
        await session.execute(delete(User))


@pytest.mark.asyncio
async def test_batch_operations_use_postgres(database: Database) -> None:
    user_id = 77801
    async with database.transaction() as session:
        session.add(User(telegram_user_id=user_id, username="batch-owner"))
        requests = [
            Request(type="url", status="pending", user_id=user_id, dedupe_hash=f"batch-{idx}")
            for idx in range(3)
        ]
        session.add_all(requests)
        await session.flush()
        session.add_all(
            [
                Summary(request_id=requests[0].id, lang="en", json_payload={}),
                Summary(request_id=requests[1].id, lang="en", json_payload={}),
            ]
        )

    batch = BatchOperations(database)
    request_ids = [request.id for request in requests]
    call_ids = await batch.async_insert_llm_calls_batch(
        [
            {
                "request_id": request_ids[0],
                "provider": "openrouter",
                "model": "qwen/qwen3-max",
                "status": "ok",
                "latency_ms": 100,
            },
            {
                "request_id": request_ids[1],
                "provider": "openrouter",
                "model": "qwen/qwen3-max",
                "status": "ok",
                "latency_ms": 200,
            },
        ]
    )
    assert len(call_ids) == 2

    assert await batch.async_update_request_statuses_batch(
        [(request_ids[0], "completed"), (request_ids[1], "completed")]
    ) == 2

    fetched_requests = await batch.async_get_requests_by_ids_batch(request_ids)
    assert [request.id for request in fetched_requests] == request_ids
    assert [request.status for request in fetched_requests[:2]] == ["completed", "completed"]

    fetched_summaries = await batch.async_get_summaries_by_request_ids_batch(request_ids)
    summary_ids = [summary.id for summary in fetched_summaries]
    assert len(summary_ids) == 2
    assert await batch.async_mark_summaries_as_read_batch(summary_ids) == 2

    assert await batch.async_delete_requests_batch([request_ids[0]]) == 1
    async with database.session() as session:
        llm_count = await session.scalar(select(func.count()).select_from(LLMCall))
        summary_count = await session.scalar(select(func.count()).select_from(Summary))

    assert llm_count == 1
    assert summary_count == 1
