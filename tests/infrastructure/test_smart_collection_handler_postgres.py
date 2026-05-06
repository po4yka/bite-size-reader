from __future__ import annotations

import datetime as dt
import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, select

from app.config.database import DatabaseConfig
from app.core.time_utils import UTC
from app.db.models import Collection, CollectionItem, Request, Summary, User
from app.db.session import Database
from app.domain.events.summary_events import SummaryCreated
from app.infrastructure.messaging.handlers.smart_collection_handler import SmartCollectionHandler

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
        await session.execute(delete(CollectionItem))
        await session.execute(delete(Collection))
        await session.execute(delete(Summary))
        await session.execute(delete(Request))
        await session.execute(delete(User))


@pytest.mark.asyncio
async def test_smart_collection_handler_populates_matching_collections(
    database: Database,
) -> None:
    async with database.transaction() as session:
        user = User(telegram_user_id=8801, username="smart-owner")
        session.add(user)
        await session.flush()
        request = Request(
            user_id=user.telegram_user_id,
            type="url",
            status="completed",
            input_url="https://arxiv.org/abs/1234",
            normalized_url="https://arxiv.org/abs/1234",
            dedupe_hash="smart-1",
        )
        session.add(request)
        await session.flush()
        summary = Summary(
            request_id=request.id,
            lang="en",
            json_payload={"title": "Paper", "summary_250": "Research"},
        )
        smart = Collection(
            user_id=user.telegram_user_id,
            name="Arxiv",
            collection_type="smart",
            query_conditions_json=[
                {"type": "domain_matches", "operator": "contains", "value": "arxiv"}
            ],
            query_match_mode="all",
            position=1,
        )
        other = Collection(
            user_id=user.telegram_user_id,
            name="GitHub",
            collection_type="smart",
            query_conditions_json=[
                {"type": "domain_matches", "operator": "contains", "value": "github"}
            ],
            query_match_mode="all",
            position=2,
        )
        session.add_all([summary, smart, other])
        await session.flush()
        summary_id = summary.id
        request_id = request.id
        smart_id = smart.id
        other_id = other.id

    handler = SmartCollectionHandler(database)
    event = SummaryCreated(
        occurred_at=dt.datetime(2026, 5, 6, tzinfo=UTC),
        summary_id=summary_id,
        request_id=request_id,
        language="en",
        has_insights=False,
    )
    await handler.on_summary_created(event)
    await handler.on_summary_created(event)

    async with database.session() as session:
        items = list(await session.scalars(select(CollectionItem)))

    assert [(item.collection_id, item.summary_id, item.position) for item in items] == [
        (smart_id, summary_id, 1)
    ]
    assert all(item.collection_id != other_id for item in items)
