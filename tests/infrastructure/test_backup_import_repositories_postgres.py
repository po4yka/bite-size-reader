"""Postgres-backed tests for backup and import-job repositories."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete

from app.config.database import DatabaseConfig
from app.db.models import ImportJob, User, UserBackup
from app.db.session import Database
from app.infrastructure.persistence.sqlite.repositories.backup_repository import (
    SqliteBackupRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.import_job_repository import (
    SqliteImportJobRepositoryAdapter,
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
        session.add(User(telegram_user_id=11001, username="backup"))
    try:
        yield db
    finally:
        await _clear(db)
        await db.dispose()


async def _clear(database: Database) -> None:
    async with database.transaction() as session:
        await session.execute(delete(ImportJob))
        await session.execute(delete(UserBackup))
        await session.execute(delete(User))


@pytest.mark.asyncio
async def test_backup_repository_crud_and_recent_count(database: Database) -> None:
    repo = SqliteBackupRepositoryAdapter(database)

    first = await repo.async_create_backup(11001, type="manual")
    second = await repo.async_create_backup(11001, type="scheduled")
    await repo.async_update_backup(
        first["id"],
        status="completed",
        file_path="/tmp/backup.json",
        file_size_bytes=100,
        items_count=3,
        ignored="ignored",
    )

    loaded = await repo.async_get_backup(first["id"])
    assert loaded is not None
    assert loaded["status"] == "completed"
    assert loaded["file_path"] == "/tmp/backup.json"
    assert await repo.async_count_recent_backups(11001, since_hours=1) == 2
    assert [row["id"] for row in await repo.async_list_backups(11001)] == [
        second["id"],
        first["id"],
    ]

    await repo.async_delete_backup(first["id"])
    assert await repo.async_get_backup(first["id"]) is None


@pytest.mark.asyncio
async def test_import_job_repository_crud_progress_and_status(database: Database) -> None:
    repo = SqliteImportJobRepositoryAdapter(database)

    job = await repo.async_create_job(
        11001,
        source_format="html",
        file_name="bookmarks.html",
        total_items=5,
        options={"dedupe": True},
    )
    await repo.async_update_progress(
        job["id"],
        processed=3,
        created=2,
        skipped=1,
        failed=0,
        errors=["warning"],
    )
    await repo.async_set_status(job["id"], "completed")

    loaded = await repo.async_get_job(job["id"])
    assert loaded is not None
    assert loaded["status"] == "completed"
    assert loaded["processed_items"] == 3
    assert loaded["created_items"] == 2
    assert loaded["skipped_items"] == 1
    assert loaded["errors_json"] == ["warning"]
    assert loaded["options_json"] == {"dedupe": True}
    assert [row["id"] for row in await repo.async_list_jobs(11001)] == [job["id"]]

    await repo.async_delete_job(job["id"])
    assert await repo.async_get_job(job["id"]) is None
