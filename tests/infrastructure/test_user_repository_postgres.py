"""Postgres-backed tests for the user repository."""

from __future__ import annotations

import datetime as dt
import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, select

from app.config.database import DatabaseConfig
from app.core.time_utils import UTC
from app.db.models import Chat, User, UserInteraction
from app.db.session import Database
from app.infrastructure.persistence.sqlite.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
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
        await session.execute(delete(UserInteraction))
        await session.execute(delete(Chat))
        await session.execute(delete(User))


@pytest.mark.asyncio
async def test_user_repository_upserts_links_preferences_and_deletes(
    database: Database,
) -> None:
    repo = SqliteUserRepositoryAdapter(database)

    created_user, created = await repo.async_get_or_create_user(
        1001, username="first", is_owner=True
    )
    same_user, created_again = await repo.async_get_or_create_user(1001, username="ignored")
    assert created is True
    assert created_again is False
    assert created_user["telegram_user_id"] == same_user["telegram_user_id"] == 1001

    await repo.async_upsert_user(telegram_user_id=1001, username="updated", is_owner=False)
    user = await repo.async_get_user_by_telegram_id(1001)
    assert user is not None
    assert user["username"] == "updated"
    assert user["is_owner"] is False

    expires_at = dt.datetime.now(UTC) + dt.timedelta(minutes=5)
    await repo.async_set_link_nonce(telegram_user_id=1001, nonce="nonce", expires_at=expires_at)
    assert (await repo.async_get_user_by_telegram_id(1001))["link_nonce"] == "nonce"

    linked_at = dt.datetime.now(UTC)
    await repo.async_complete_telegram_link(
        telegram_user_id=1001,
        linked_telegram_user_id=2002,
        username="linked",
        photo_url="https://example.com/photo.jpg",
        first_name="First",
        last_name="Last",
        linked_at=linked_at,
    )
    linked = await repo.async_get_user_by_telegram_id(1001)
    assert linked["linked_telegram_user_id"] == 2002
    assert linked["link_nonce"] is None

    await repo.async_unlink_telegram(telegram_user_id=1001)
    assert (await repo.async_get_user_by_telegram_id(1001))["linked_telegram_user_id"] is None

    await repo.async_update_user_preferences(1001, {"lang": "en"})
    assert (await repo.async_get_user_by_telegram_id(1001))["preferences_json"] == {"lang": "en"}
    assert await repo.async_get_max_server_version(1001) is not None

    await repo.async_delete_user(telegram_user_id=1001)
    assert await repo.async_get_user_by_telegram_id(1001) is None


@pytest.mark.asyncio
async def test_user_repository_chats_and_interactions(database: Database) -> None:
    repo = SqliteUserRepositoryAdapter(database)
    await repo.async_upsert_user(telegram_user_id=3003, username="interaction")
    await repo.async_upsert_chat(chat_id=4004, type_="private", title="Old", username="old")
    await repo.async_upsert_chat(chat_id=4004, type_="group", title="New", username="new")

    async with database.session() as session:
        chat = await session.scalar(select(Chat).where(Chat.chat_id == 4004))
    assert chat is not None
    assert chat.type == "group"
    assert chat.title == "New"

    interaction_id = await repo.async_insert_user_interaction(
        user_id=3003,
        chat_id=4004,
        message_id=55,
        interaction_type="command",
        command="/start",
        input_text="hello",
        correlation_id="user-repo",
        structured_output_enabled=True,
    )
    await repo.async_update_user_interaction(
        interaction_id,
        updates={"response_sent": True, "unknown_field": "ignored"},
        response_type="summary",
    )

    rows = await repo.async_get_user_interactions(uid=3003)
    assert len(rows) == 1
    assert rows[0]["id"] == interaction_id
    assert rows[0]["response_sent"] is True
    assert rows[0]["response_type"] == "summary"
