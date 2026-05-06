from __future__ import annotations

import os
import zipfile
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, select

from app.config.database import DatabaseConfig
from app.db.models import Request, Summary, User, UserBackup
from app.db.session import Database
from app.infrastructure.persistence.sqlite.backup_archive_service import (
    async_create_backup_archive,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path


def _test_dsn() -> str:
    return os.getenv("TEST_DATABASE_URL", "")


@pytest.fixture
async def database() -> AsyncGenerator[Database]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for Postgres backup archive tests")

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
        await session.execute(delete(Summary))
        await session.execute(delete(Request))
        await session.execute(delete(UserBackup))
        await session.execute(delete(User))


@pytest.mark.asyncio
async def test_create_backup_archive_uses_postgres_session(
    database: Database,
    tmp_path: Path,
) -> None:
    user_id = 12001
    async with database.transaction() as session:
        session.add(User(telegram_user_id=user_id, username="archive"))
        request = Request(
            type="url",
            status="completed",
            user_id=user_id,
            input_url="https://example.com",
            normalized_url="https://example.com",
            dedupe_hash="archive-example",
        )
        session.add(request)
        await session.flush()
        session.add(
            Summary(
                request_id=request.id,
                lang="en",
                json_payload={"tldr": "Archived"},
            )
        )
        backup = UserBackup(user_id=user_id, type="manual", status="pending")
        session.add(backup)
        await session.flush()
        backup_id = backup.id

    await async_create_backup_archive(
        user_id=user_id,
        backup_id=backup_id,
        db=database,
        data_dir=str(tmp_path),
    )

    async with database.session() as session:
        backup = await session.scalar(select(UserBackup).where(UserBackup.id == backup_id))
    assert backup is not None
    assert backup.status == "completed"
    assert backup.file_path is not None
    assert backup.items_count == 1

    with zipfile.ZipFile(backup.file_path) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "requests.json" in names
    assert "summaries.json" in names
