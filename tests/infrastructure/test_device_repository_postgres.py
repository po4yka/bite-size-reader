"""Postgres-backed tests for the device repository."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete

from app.config.database import DatabaseConfig
from app.db.models import User, UserDevice
from app.db.session import Database
from app.infrastructure.persistence.repositories.device_repository import (
    SqliteDeviceRepositoryAdapter,
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
    async with db.transaction() as session:
        session.add(User(telegram_user_id=10001, username="device"))
        session.add(User(telegram_user_id=10002, username="device-two"))
    try:
        yield db
    finally:
        await _clear(db)
        await db.dispose()


async def _clear(database: Database) -> None:
    async with database.transaction() as session:
        await session.execute(delete(UserDevice))
        await session.execute(delete(User))


@pytest.mark.asyncio
async def test_device_repository_registers_updates_and_lists(database: Database) -> None:
    repo = SqliteDeviceRepositoryAdapter(database)

    device_id = await repo.async_register_device(
        user_id=10001,
        token="token-a",
        platform="ios",
        device_id="device-a",
    )
    row = await repo.async_get_device_by_token("token-a")
    assert row is not None
    assert row["id"] == device_id
    assert row["platform"] == "ios"

    await repo.async_update_device(
        "token-a",
        user_id=10002,
        platform="android",
        device_id="device-b",
    )
    updated = await repo.async_get_device_by_token("token-a")
    assert updated["user_id"] == 10002
    assert updated["platform"] == "android"
    assert [item["id"] for item in await repo.async_list_user_devices(10002)] == [device_id]
    assert await repo.async_deactivate_device("token-a") is True
    assert await repo.async_deactivate_device("missing") is False
    assert await repo.async_list_user_devices(10002) == []
    assert [
        item["id"] for item in await repo.async_list_user_devices(10002, active_only=False)
    ] == [device_id]


@pytest.mark.asyncio
async def test_device_repository_upserts_and_updates_last_seen(database: Database) -> None:
    repo = SqliteDeviceRepositoryAdapter(database)

    first_id = await repo.async_upsert_device(
        user_id=10001,
        token="token-b",
        platform="ios",
        device_id="first",
    )
    before = await repo.async_get_device_by_token("token-b")
    second_id = await repo.async_upsert_device(
        user_id=10001,
        token="token-b",
        platform="ios",
        device_id="second",
    )
    await repo.async_update_last_seen("token-b")
    after = await repo.async_get_device_by_token("token-b")

    assert second_id == first_id
    assert after["device_id"] == "second"
    assert after["last_seen_at"] >= before["last_seen_at"]


@pytest.mark.asyncio
async def test_device_repository_requires_existing_user(database: Database) -> None:
    repo = SqliteDeviceRepositoryAdapter(database)

    with pytest.raises(ValueError, match="User 999999 not found"):
        await repo.async_register_device(user_id=999999, token="missing", platform="ios")
