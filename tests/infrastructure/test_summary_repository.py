"""Behavioral tests for SqliteSummaryRepositoryAdapter using in-memory SQLite."""

from __future__ import annotations

import asyncio

import peewee
import pytest

from app.db.models import Request, Summary, database_proxy
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)


class _SyncSession:
    """Minimal session adapter that runs sync DB operations in the calling thread."""

    def __init__(self, db: peewee.Database) -> None:
        self.database = db

    async def async_execute(self, operation, *args, **kwargs):
        return await asyncio.to_thread(operation, *args)

    async def async_execute_transaction(self, operation, *args, **kwargs):
        return await asyncio.to_thread(operation, *args)


@pytest.fixture
def in_memory_db(tmp_path):
    old_db = database_proxy.obj
    db = peewee.SqliteDatabase(
        str(tmp_path / "test_summary_repo.db"), pragmas={"journal_mode": "wal"}
    )
    database_proxy.initialize(db)
    db.bind([Request, Summary], bind_refs=False, bind_backrefs=False)
    db.create_tables([Request, Summary])
    yield db
    db.drop_tables([Summary, Request])
    db.close()
    database_proxy.initialize(old_db)
    for model in (Request, Summary):
        model._meta.database = database_proxy


@pytest.fixture
def repo(in_memory_db):
    return SqliteSummaryRepositoryAdapter(_SyncSession(in_memory_db))


def _create_request(user_id: int = 1, url: str = "https://example.com") -> Request:
    return Request.create(
        type="url",
        status="pending",
        correlation_id=f"cid-{url}",
        user_id=user_id,
        input_url=url,
        normalized_url=url,
        dedupe_hash=f"hash-{url}",
    )


@pytest.mark.asyncio
async def test_upsert_and_get_summary(in_memory_db, repo):
    req = _create_request()
    payload = {"summary_250": "short", "summary_1000": "long"}

    summary_id = await repo.async_upsert_summary(req.id, "en", payload)

    assert isinstance(summary_id, int)
    assert summary_id > 0

    result = await repo.async_get_summary_by_request(req.id)
    assert result is not None
    # model_to_dict returns the FK as a bare int (the request id)
    assert result["request"] == req.id
    assert result["lang"] == "en"


@pytest.mark.asyncio
async def test_upsert_summary_second_call_updates_payload(in_memory_db, repo):
    req = _create_request(url="https://idempotent.com")

    v1 = await repo.async_upsert_summary(req.id, "en", {"summary_250": "v1"})
    v2 = await repo.async_upsert_summary(req.id, "en", {"summary_250": "v2"})

    # Both return a version (monotonic int), second must be >= first
    assert isinstance(v1, int)
    assert isinstance(v2, int)
    assert v2 >= v1
    result = await repo.async_get_summary_by_request(req.id)
    assert result["json_payload"]["summary_250"] == "v2"


@pytest.mark.asyncio
async def test_mark_as_read_and_unread(in_memory_db, repo):
    req = _create_request(url="https://read-test.com")
    await repo.async_upsert_summary(req.id, "en", {"summary_250": "text"})
    summary = await repo.async_get_summary_by_request(req.id)
    summary_id = summary["id"]

    assert summary["is_read"] is False

    await repo.async_mark_summary_as_read(summary_id)
    updated = await repo.async_get_summary_by_request(req.id)
    assert updated["is_read"] is True

    await repo.async_mark_summary_as_unread(summary_id)
    reverted = await repo.async_get_summary_by_request(req.id)
    assert reverted["is_read"] is False


@pytest.mark.asyncio
async def test_get_summary_by_id_returns_none_for_missing(repo):
    result = await repo.async_get_summary_by_id(9999)
    assert result is None


@pytest.mark.asyncio
async def test_get_summary_by_request_returns_none_for_missing(repo):
    result = await repo.async_get_summary_by_request(9999)
    assert result is None
