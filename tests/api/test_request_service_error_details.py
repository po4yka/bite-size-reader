"""Tests for request error-detail derivation."""

import datetime as dt

import peewee
import pytest

from app.core.time_utils import UTC
from app.cli._legacy_peewee_models import CrawlResult, LLMCall, Request, Summary, database_proxy
from tests.api.request_service_helpers import build_request_service


@pytest.fixture
def in_memory_db(tmp_path):
    old_db = database_proxy.obj
    db_path = str(tmp_path / "test_error_details.db")
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


def _create_request(user_id: int, dedupe_hash: str, *, correlation_id: str = "cid-1") -> Request:
    return Request.create(
        type="url",
        status="error",
        correlation_id=correlation_id,
        user_id=user_id,
        input_url="https://example.com",
        normalized_url="https://example.com",
        dedupe_hash=dedupe_hash,
        lang_detected="en",
    )


@pytest.mark.asyncio
async def test_status_code_and_message_from_error_context(in_memory_db):
    req = _create_request(user_id=10, dedupe_hash="hash-ec1", correlation_id="cid-ec1")
    LLMCall.create(
        request=req,
        status="error",
        error_text=None,
        error_context_json={
            "status_code": 429,
            "message": "Rate limit exceeded",
            "api_error": "too_many_requests",
        },
        updated_at=dt.datetime.now(UTC),
    )

    status_info = await build_request_service(in_memory_db).get_request_status(req.user_id, req.id)

    assert status_info.error_details is not None
    assert status_info.error_details.stage == "llm_summarization"
    assert status_info.error_details.error_type == 429
    assert status_info.error_details.error_message == "Rate limit exceeded"


@pytest.mark.asyncio
async def test_error_text_takes_precedence_over_context_message(in_memory_db):
    req = _create_request(user_id=11, dedupe_hash="hash-ec2", correlation_id="cid-ec2")
    LLMCall.create(
        request=req,
        status="error",
        error_text="explicit error text",
        error_context_json={
            "status_code": 500,
            "message": "Internal server error",
            "api_error": "server_error",
        },
        updated_at=dt.datetime.now(UTC),
    )

    status_info = await build_request_service(in_memory_db).get_request_status(req.user_id, req.id)

    assert status_info.error_details is not None
    assert status_info.error_details.stage == "llm_summarization"
    assert status_info.error_details.error_type == 500
    assert status_info.error_details.error_message == "explicit error text"


@pytest.mark.asyncio
async def test_falls_back_when_error_context_empty(in_memory_db):
    req = _create_request(user_id=12, dedupe_hash="hash-ec3", correlation_id="cid-ec3")
    LLMCall.create(
        request=req,
        status="error",
        error_text=None,
        error_context_json={},
        updated_at=dt.datetime.now(UTC),
    )

    status_info = await build_request_service(in_memory_db).get_request_status(req.user_id, req.id)

    assert status_info.error_details is not None
    assert status_info.error_details.stage == "llm_summarization"
    assert status_info.error_details.error_type == "LLM_FAILED"
    assert status_info.error_details.error_message == "LLM summarization failed"
