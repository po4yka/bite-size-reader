from __future__ import annotations

import peewee
import pytest

from app.db.models import Request, Summary, database_proxy
from app.db.runtime.operation_executor import DatabaseOperationExecutor
from app.db.rw_lock import AsyncRWLock
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)


@pytest.fixture
def in_memory_db(tmp_path):
    old_db = database_proxy.obj
    db_path = str(tmp_path / "test_summary_repository_finalize.db")
    db = peewee.SqliteDatabase(db_path, pragmas={"journal_mode": "wal"})
    database_proxy.initialize(db)
    db.bind([Request, Summary], bind_refs=False, bind_backrefs=False)
    db.create_tables([Request, Summary])
    executor = DatabaseOperationExecutor(
        database=db,
        rw_lock=AsyncRWLock(),
        operation_timeout=30.0,
        max_retries=0,
    )
    yield db, executor
    db.drop_tables([Request, Summary])
    db.close()
    database_proxy.initialize(old_db)
    for model in [Request, Summary]:
        model._meta.database = database_proxy


@pytest.mark.asyncio
async def test_finalize_request_summary_updates_summary_and_request_status(in_memory_db) -> None:
    _db, executor = in_memory_db
    request = Request.create(
        type="url",
        status="processing",
        correlation_id="cid-finalize",
        user_id=1,
        input_url="https://example.com/finalize",
        normalized_url="https://example.com/finalize",
        dedupe_hash="hash-finalize",
    )
    repo = SqliteSummaryRepositoryAdapter(executor)

    version = await repo.async_finalize_request_summary(
        request_id=request.id,
        lang="en",
        json_payload={"tldr": "TLDR", "summary_250": "Summary", "key_ideas": ["idea"]},
        is_read=True,
    )

    summary = Summary.get(Summary.request == request.id)
    request = Request.get_by_id(request.id)

    assert version == summary.version
    assert summary.lang == "en"
    assert summary.is_read is True
    assert request.status == "ok"
