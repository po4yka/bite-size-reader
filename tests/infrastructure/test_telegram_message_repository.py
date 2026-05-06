"""Postgres-backed tests for the Telegram message repository."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete

from app.config.database import DatabaseConfig
from app.db.models import Request, TelegramMessage
from app.db.session import Database
from app.infrastructure.persistence.sqlite.repositories.telegram_message_repository import (
    SqliteTelegramMessageRepositoryAdapter,
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
        await session.execute(delete(TelegramMessage))
        await session.execute(delete(Request))


async def _request(database: Database, *, user_id: int = 7007) -> Request:
    async with database.transaction() as session:
        request = Request(
            type="url",
            status="pending",
            correlation_id=f"telegram-{user_id}",
            user_id=user_id,
            input_url=f"https://example.com/telegram/{user_id}",
            normalized_url=f"https://example.com/telegram/{user_id}",
            dedupe_hash=f"telegram-{user_id}",
        )
        session.add(request)
        await session.flush()
        return request


@pytest.mark.asyncio
async def test_telegram_message_repository_is_idempotent_and_reads_forward_info(
    database: Database,
) -> None:
    repo = SqliteTelegramMessageRepositoryAdapter(database)
    request = await _request(database)

    first_id = await repo.async_insert_telegram_message(
        request_id=request.id,
        message_id=11,
        chat_id=22,
        date_ts=33,
        text_full="hello",
        entities_json=[{"type": "url"}],
        media_type="photo",
        media_file_ids_json=["file-id"],
        forward_from_chat_id=44,
        forward_from_chat_type="channel",
        forward_from_chat_title="Source",
        forward_from_message_id=55,
        forward_date_ts=66,
        telegram_raw_json={"id": 11},
    )
    duplicate_id = await repo.async_insert_telegram_message(
        request_id=request.id,
        message_id=11,
        chat_id=22,
        date_ts=33,
        text_full="ignored",
        entities_json=[],
        media_type=None,
        media_file_ids_json=[],
        forward_from_chat_id=None,
        forward_from_chat_type=None,
        forward_from_chat_title=None,
        forward_from_message_id=None,
        forward_date_ts=None,
        telegram_raw_json={},
    )

    assert duplicate_id == first_id
    row = await repo.async_get_telegram_message_by_request(request.id)
    assert row is not None
    assert row["text_full"] == "hello"
    assert row["entities_json"] == [{"type": "url"}]
    assert await repo.async_get_forward_info(request.id) == {
        "forward_from_chat_id": 44,
        "forward_from_chat_type": "channel",
        "forward_from_chat_title": "Source",
        "forward_from_message_id": 55,
        "forward_date_ts": 66,
    }


@pytest.mark.asyncio
async def test_telegram_message_repository_lists_for_user(database: Database) -> None:
    repo = SqliteTelegramMessageRepositoryAdapter(database)
    request_a = await _request(database, user_id=8008)
    request_b = await _request(database, user_id=8009)
    inserted_a = await repo.async_insert_telegram_message(
        request_id=request_a.id,
        message_id=1,
        chat_id=1,
        date_ts=1,
        text_full="a",
        entities_json=[],
        media_type=None,
        media_file_ids_json=[],
        forward_from_chat_id=None,
        forward_from_chat_type=None,
        forward_from_chat_title=None,
        forward_from_message_id=None,
        forward_date_ts=None,
        telegram_raw_json={},
    )
    await repo.async_insert_telegram_message(
        request_id=request_b.id,
        message_id=2,
        chat_id=2,
        date_ts=2,
        text_full="b",
        entities_json=[],
        media_type=None,
        media_file_ids_json=[],
        forward_from_chat_id=None,
        forward_from_chat_type=None,
        forward_from_chat_title=None,
        forward_from_message_id=None,
        forward_date_ts=None,
        telegram_raw_json={},
    )

    assert [row["id"] for row in await repo.async_get_telegram_messages_for_user(8008)] == [
        inserted_a
    ]
    assert [row["id"] for row in await repo.async_get_all_for_user(8008)] == [inserted_a]
