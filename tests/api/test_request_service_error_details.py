"""Tests for request error-detail derivation paths."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.models import LLMCall, Request
from tests.api.request_service_helpers import build_request_service

if TYPE_CHECKING:
    from app.db.session import Database


async def _create_request(
    db: Database, *, user_id: int, dedupe_hash: str, correlation_id: str = "cid-1"
) -> int:
    async with db.transaction() as session:
        request = Request(
            type="url",
            status="error",
            correlation_id=correlation_id,
            user_id=user_id,
            input_url="https://example.com",
            normalized_url="https://example.com",
            dedupe_hash=dedupe_hash,
            lang_detected="en",
        )
        session.add(request)
        await session.flush()
        return int(request.id)


async def test_status_code_and_message_from_error_context(db: Database) -> None:
    request_id = await _create_request(
        db, user_id=10, dedupe_hash="hash-ec1", correlation_id="cid-ec1"
    )
    async with db.transaction() as session:
        session.add(
            LLMCall(
                request_id=request_id,
                status="error",
                error_text=None,
                error_context_json={
                    "status_code": 429,
                    "message": "Rate limit exceeded",
                    "api_error": "too_many_requests",
                },
            )
        )

    status_info = await build_request_service(db).get_request_status(10, request_id)

    assert status_info.error_details is not None
    assert status_info.error_details.stage == "llm_summarization"
    assert status_info.error_details.error_type == 429
    assert status_info.error_details.error_message == "Rate limit exceeded"


async def test_error_text_takes_precedence_over_context_message(db: Database) -> None:
    request_id = await _create_request(
        db, user_id=11, dedupe_hash="hash-ec2", correlation_id="cid-ec2"
    )
    async with db.transaction() as session:
        session.add(
            LLMCall(
                request_id=request_id,
                status="error",
                error_text="explicit error text",
                error_context_json={
                    "status_code": 500,
                    "message": "Internal server error",
                    "api_error": "server_error",
                },
            )
        )

    status_info = await build_request_service(db).get_request_status(11, request_id)

    assert status_info.error_details is not None
    assert status_info.error_details.stage == "llm_summarization"
    assert status_info.error_details.error_type == 500
    assert status_info.error_details.error_message == "explicit error text"


async def test_falls_back_when_error_context_empty(db: Database) -> None:
    request_id = await _create_request(
        db, user_id=12, dedupe_hash="hash-ec3", correlation_id="cid-ec3"
    )
    async with db.transaction() as session:
        session.add(
            LLMCall(
                request_id=request_id,
                status="error",
                error_text=None,
                error_context_json={},
            )
        )

    status_info = await build_request_service(db).get_request_status(12, request_id)

    assert status_info.error_details is not None
    assert status_info.error_details.stage == "llm_summarization"
    assert status_info.error_details.error_type == "LLM_FAILED"
    assert status_info.error_details.error_message == "LLM summarization failed"
