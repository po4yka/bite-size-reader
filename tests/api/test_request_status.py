import datetime as dt

import peewee
import pytest

from app.api.services.request_service import RequestService
from app.core.time_utils import UTC
from app.db.models import CrawlResult, LLMCall, Request, database_proxy


@pytest.fixture
def in_memory_db(tmp_path):
    # Save old proxy state
    old_db = database_proxy.obj

    # Use a file-based database instead of :memory: because asyncio.to_thread
    # runs operations in separate threads, and SQLite in-memory databases
    # are thread-local by default
    db_path = str(tmp_path / "test_request_status.db")
    db = peewee.SqliteDatabase(db_path, pragmas={"journal_mode": "wal"})
    database_proxy.initialize(db)
    db.bind([Request, CrawlResult, LLMCall], bind_refs=False, bind_backrefs=False)
    db.create_tables([Request, CrawlResult, LLMCall])
    yield db
    db.drop_tables([Request, CrawlResult, LLMCall])
    db.close()

    # Restore old proxy state
    database_proxy.initialize(old_db)

    # IMPORTANT: Rebind models to database_proxy so subsequent tests don't use the closed db.
    # The bind() call above permanently sets model._meta.database to `db`, so we need to
    # restore it to the proxy to allow other fixtures to properly initialize models.
    for model in [Request, CrawlResult, LLMCall]:
        model._meta.database = database_proxy


def _create_request(
    user_id: int,
    dedupe_hash: str,
    *,
    status: str = "error",
    correlation_id: str = "cid-1",
) -> Request:
    return Request.create(
        type="url",
        status=status,
        correlation_id=correlation_id,
        user_id=user_id,
        input_url="https://example.com",
        normalized_url="https://example.com",
        dedupe_hash=dedupe_hash,
        lang_detected="en",
    )


@pytest.mark.asyncio
async def test_status_includes_crawl_error(in_memory_db):
    req = _create_request(user_id=1, dedupe_hash="hash-1", correlation_id="cid-crawl")

    CrawlResult.create(
        request=req,
        status="error",
        error_text="firecrawl failed to fetch",
        updated_at=dt.datetime.now(UTC),
    )

    status_info = await RequestService.get_request_status(req.user_id, req.id)

    assert status_info["status"] == "error"
    assert status_info["error_stage"] == "content_extraction"
    assert status_info["error_type"] == "EXTRACTION_FAILED"
    assert status_info["error_message"] == "firecrawl failed to fetch"
    assert status_info["correlation_id"] == "cid-crawl"
    assert status_info["can_retry"] is True


@pytest.mark.asyncio
async def test_status_prefers_llm_error_when_available(in_memory_db):
    req = _create_request(user_id=2, dedupe_hash="hash-2", correlation_id="cid-llm")

    LLMCall.create(
        request=req,
        status="error",
        error_text="llm summary failed",
        error_context_json={"error_code": "LLM_FAILED"},
        updated_at=dt.datetime.now(UTC),
    )

    status_info = await RequestService.get_request_status(req.user_id, req.id)

    assert status_info["status"] == "error"
    assert status_info["error_stage"] == "llm_summarization"
    assert status_info["error_type"] == "LLM_FAILED"
    assert status_info["error_message"] == "llm summary failed"
    assert status_info["correlation_id"] == "cid-llm"
    assert status_info["can_retry"] is True
