"""Tests for _derive_error_details reading the correct error_context keys.

The error_context_json produced by openrouter_client.py / response_processor.py
uses keys ``status_code``, ``message``, and ``api_error``.  The consumer
(_derive_error_details) must read those exact keys.
"""

import datetime as dt

import peewee
import pytest

from app.api.services.request_service import RequestService
from app.core.time_utils import UTC
from app.db.models import CrawlResult, LLMCall, Request, database_proxy


@pytest.fixture
def in_memory_db(tmp_path):
    old_db = database_proxy.obj

    db_path = str(tmp_path / "test_error_details.db")
    db = peewee.SqliteDatabase(db_path, pragmas={"journal_mode": "wal"})
    database_proxy.initialize(db)
    db.bind([Request, CrawlResult, LLMCall], bind_refs=False, bind_backrefs=False)
    db.create_tables([Request, CrawlResult, LLMCall])
    yield db
    db.drop_tables([Request, CrawlResult, LLMCall])
    db.close()

    database_proxy.initialize(old_db)
    for model in [Request, CrawlResult, LLMCall]:
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
    """error_type should come from 'status_code', message from 'message'."""
    req = _create_request(user_id=10, dedupe_hash="hash-ec1", correlation_id="cid-ec1")

    LLMCall.create(
        request=req,
        status="error",
        error_text=None,  # force fallback to error_context for message
        error_context_json={
            "status_code": 429,
            "message": "Rate limit exceeded",
            "api_error": "too_many_requests",
        },
        updated_at=dt.datetime.now(UTC),
    )

    status_info = await RequestService.get_request_status(req.user_id, req.id)

    assert status_info["error_stage"] == "llm_summarization"
    assert status_info["error_type"] == 429, "error_type must read 'status_code', not 'error_code'"
    assert status_info["error_message"] == "Rate limit exceeded", (
        "error_message must read 'message', not 'error_message'"
    )


@pytest.mark.asyncio
async def test_error_text_takes_precedence_over_context_message(in_memory_db):
    """When error_text is set, it should be used instead of context['message']."""
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

    status_info = await RequestService.get_request_status(req.user_id, req.id)

    assert status_info["error_stage"] == "llm_summarization"
    assert status_info["error_type"] == 500
    assert status_info["error_message"] == "explicit error text"
