from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete

from app.config.database import DatabaseConfig
from app.db.models import Collection, CollectionItem, Request, Summary, SummaryTag, Tag, User
from app.db.session import Database
from app.infrastructure.rules.collection_membership import SqliteCollectionMembershipAdapter
from app.infrastructure.rules.context import SqliteRuleContextAdapter

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
        await session.execute(delete(SummaryTag))
        await session.execute(delete(Tag))
        await session.execute(delete(Summary))
        await session.execute(delete(Request))
        await session.execute(delete(User))


async def _seed_summary(database: Database) -> tuple[int, int, int]:
    async with database.transaction() as session:
        user = User(telegram_user_id=8701, username="rules-owner")
        session.add(user)
        await session.flush()
        request = Request(
            user_id=user.telegram_user_id,
            type="url",
            status="completed",
            input_url="https://example.com/rules",
            normalized_url="https://example.com/rules",
            dedupe_hash="rules-1",
        )
        session.add(request)
        await session.flush()
        summary = Summary(
            request_id=request.id,
            lang="en",
            json_payload={
                "title": "Rules Title",
                "summary_250": "Rules content",
                "metadata": {"domain": "example.com"},
            },
        )
        collection = Collection(
            user_id=user.telegram_user_id,
            name="Rules",
            position=1,
        )
        tag = Tag(user_id=user.telegram_user_id, name="AI", normalized_name="ai")
        session.add_all([summary, collection, tag])
        await session.flush()
        session.add(SummaryTag(summary_id=summary.id, tag_id=tag.id, source="manual"))
        return user.telegram_user_id, summary.id, collection.id


@pytest.mark.asyncio
async def test_rule_context_adapter_builds_context_from_postgres(database: Database) -> None:
    _user_id, summary_id, _collection_id = await _seed_summary(database)
    adapter = SqliteRuleContextAdapter(database)

    context = await adapter.async_build_context({"summary_id": summary_id})

    assert context.title == "Rules Title"
    assert context.tags == ["ai"]
    assert context.summary_snapshot is not None
    assert context.summary_snapshot["id"] == summary_id


@pytest.mark.asyncio
async def test_collection_membership_adapter_adds_and_removes_items(
    database: Database,
) -> None:
    user_id, summary_id, collection_id = await _seed_summary(database)
    adapter = SqliteCollectionMembershipAdapter(database)

    assert (
        await adapter.async_add_summary(
            user_id=user_id,
            collection_id=collection_id,
            summary_id=summary_id,
        )
        == f"added to collection {collection_id}"
    )
    assert (
        await adapter.async_add_summary(
            user_id=user_id,
            collection_id=collection_id,
            summary_id=summary_id,
        )
        == f"already in collection {collection_id}"
    )
    assert (
        await adapter.async_remove_summary(
            user_id=user_id,
            collection_id=collection_id,
            summary_id=summary_id,
        )
        == f"removed from collection {collection_id}"
    )
    assert (
        await adapter.async_remove_summary(
            user_id=user_id,
            collection_id=collection_id,
            summary_id=summary_id,
        )
        == "not in collection"
    )
