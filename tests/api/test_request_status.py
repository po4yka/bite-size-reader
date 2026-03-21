import datetime as dt

import peewee
import pytest

from app.core.time_utils import UTC
from app.db.models import CrawlResult, LLMCall, Request, Summary, database_proxy
from tests.api.request_service_helpers import build_request_service


@pytest.fixture
def in_memory_db(tmp_path):
    old_db = database_proxy.obj
    db_path = str(tmp_path / "test_request_status.db")
    db = peewee.SqliteDatabase(db_path, pragmas={"journal_mode": "wal"})
    database_proxy.initialize(db)
    db.bind([Request, CrawlResult, LLMCall, Summary], bind_refs=False, bind_backrefs=False)
    db.create_tables([Request, CrawlResult, LLMCall, Summary])
    yield db
    db.drop_tables([Request, CrawlResult, LLMCall, Summary])
    db.close()
    database_proxy.initialize(old_db)
    for model in [Request, CrawlResult, LLMCall, Summary]:
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

    status_info = await build_request_service(in_memory_db).get_request_status(req.user_id, req.id)

    assert status_info.status == "error"
    assert status_info.error_details is not None
    assert status_info.error_details.stage == "content_extraction"
    assert status_info.error_details.error_type == "EXTRACTION_FAILED"
    assert status_info.error_details.error_message == "firecrawl failed to fetch"
    assert status_info.correlation_id == "cid-crawl"
    assert status_info.can_retry is True


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

    status_info = await build_request_service(in_memory_db).get_request_status(req.user_id, req.id)

    assert status_info.status == "error"
    assert status_info.error_details is not None
    assert status_info.error_details.stage == "llm_summarization"
    assert status_info.error_details.error_type == "LLM_FAILED"
    assert status_info.error_details.error_message == "llm summary failed"
    assert status_info.correlation_id == "cid-llm"
    assert status_info.can_retry is True


@pytest.mark.asyncio
async def test_status_uses_request_error_context_snapshot_when_present(in_memory_db):
    req = _create_request(user_id=3, dedupe_hash="hash-3", correlation_id="cid-snapshot")
    req.error_context_json = {
        "pipeline": "url_extraction",
        "stage": "extraction",
        "component": "firecrawl",
        "reason_code": "FIRECRAWL_ERROR",
        "error_type": "ValueError",
        "error_message": "normalized error",
        "retryable": True,
        "attempt": 1,
        "max_attempts": 3,
        "timestamp": "2026-02-28T10:00:00Z",
    }
    req.save()

    status_info = await build_request_service(in_memory_db).get_request_status(req.user_id, req.id)

    assert status_info.error_details is not None
    assert status_info.error_details.stage == "extraction"
    assert status_info.error_details.error_reason_code == "FIRECRAWL_ERROR"
    assert status_info.error_details.retryable is True
    assert status_info.error_details.debug["component"] == "firecrawl"
