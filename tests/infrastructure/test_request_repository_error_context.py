from __future__ import annotations

import peewee
import pytest

from app.db.models import Request, database_proxy
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)


@pytest.fixture
def in_memory_db(tmp_path):
    old_db = database_proxy.obj
    db_path = str(tmp_path / "test_request_repo_error_context.db")
    db = peewee.SqliteDatabase(db_path, pragmas={"journal_mode": "wal"})
    database_proxy.initialize(db)
    db.bind([Request], bind_refs=False, bind_backrefs=False)
    db.create_tables([Request])
    yield db
    db.drop_tables([Request])
    db.close()
    database_proxy.initialize(old_db)
    Request._meta.database = database_proxy


@pytest.mark.asyncio
async def test_async_update_request_error_persists_error_context_json(in_memory_db):
    req = Request.create(
        type="url",
        status="pending",
        correlation_id="cid-r1",
        user_id=1,
        input_url="https://example.com",
        normalized_url="https://example.com",
        dedupe_hash="hash-r1",
    )
    repo = SqliteRequestRepositoryAdapter(database_proxy)

    await repo.async_update_request_error(
        req.id,
        "error",
        error_type="FIRECRAWL_ERROR",
        error_message="normalized failure",
        processing_time_ms=123,
        error_context_json={
            "stage": "extraction",
            "component": "firecrawl",
            "reason_code": "FIRECRAWL_ERROR",
            "retryable": True,
        },
    )

    row = Request.get_by_id(req.id)
    assert row.status == "error"
    assert row.error_type == "FIRECRAWL_ERROR"
    assert row.error_message == "normalized failure"
    assert row.processing_time_ms == 123
    assert isinstance(row.error_context_json, dict)
    assert row.error_context_json["reason_code"] == "FIRECRAWL_ERROR"
