"""Tests for RequestService.get_request_status error-detail surfacing."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import update

from app.core.time_utils import UTC
from app.db.models import CrawlResult, LLMCall, Request
from tests.api.request_service_helpers import build_request_service

if TYPE_CHECKING:
    from app.db.session import Database


async def _create_request(
    db: Database,
    *,
    user_id: int,
    dedupe_hash: str,
    status: str = "error",
    correlation_id: str = "cid-1",
) -> int:
    async with db.transaction() as session:
        request = Request(
            type="url",
            status=status,
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


async def test_status_includes_crawl_error(db: Database) -> None:
    request_id = await _create_request(
        db, user_id=1, dedupe_hash="hash-1", correlation_id="cid-crawl"
    )
    async with db.transaction() as session:
        session.add(
            CrawlResult(
                request_id=request_id,
                status="error",
                error_text="firecrawl failed to fetch",
                updated_at=dt.datetime.now(UTC),
            )
        )

    status_info = await build_request_service(db).get_request_status(1, request_id)

    assert status_info.status == "failed"
    assert status_info.legacy_status == "error"
    assert status_info.error_details is not None
    assert status_info.error_details.stage == "content_extraction"
    assert status_info.error_details.error_type == "EXTRACTION_FAILED"
    assert status_info.error_details.error_message == "firecrawl failed to fetch"
    assert status_info.correlation_id == "cid-crawl"
    assert status_info.can_retry is True


async def test_status_prefers_llm_error_when_available(db: Database) -> None:
    request_id = await _create_request(
        db, user_id=2, dedupe_hash="hash-2", correlation_id="cid-llm"
    )
    async with db.transaction() as session:
        session.add(
            LLMCall(
                request_id=request_id,
                status="error",
                error_text="llm summary failed",
                error_context_json={"error_code": "LLM_FAILED"},
            )
        )

    status_info = await build_request_service(db).get_request_status(2, request_id)

    assert status_info.status == "failed"
    assert status_info.legacy_status == "error"
    assert status_info.error_details is not None
    assert status_info.error_details.stage == "llm_summarization"
    assert status_info.error_details.error_type == "LLM_FAILED"
    assert status_info.error_details.error_message == "llm summary failed"
    assert status_info.correlation_id == "cid-llm"
    assert status_info.can_retry is True


async def test_status_uses_request_error_context_snapshot_when_present(
    db: Database,
) -> None:
    request_id = await _create_request(
        db, user_id=3, dedupe_hash="hash-3", correlation_id="cid-snapshot"
    )
    async with db.transaction() as session:
        await session.execute(
            update(Request)
            .where(Request.id == request_id)
            .values(
                error_context_json={
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
            )
        )

    status_info = await build_request_service(db).get_request_status(3, request_id)

    assert status_info.error_details is not None
    assert status_info.error_details.stage == "extraction"
    assert status_info.error_details.error_reason_code == "FIRECRAWL_ERROR"
    assert status_info.error_details.retryable is True
    assert status_info.error_details.debug["component"] == "firecrawl"


@pytest.mark.parametrize(
    ("legacy_status", "public_status", "public_stage"),
    [
        ("pending", "pending", "queued"),
        ("processing", "running", "extracting"),
        ("success", "succeeded", "done"),
        ("complete", "succeeded", "done"),
        ("failed", "failed", "done"),
        ("error", "failed", "done"),
    ],
)
async def test_status_projects_legacy_db_values_to_public_lifecycle(
    db: Database,
    legacy_status: str,
    public_status: str,
    public_stage: str,
) -> None:
    request_id = await _create_request(
        db,
        user_id=4,
        dedupe_hash=f"hash-{legacy_status}",
        status=legacy_status,
        correlation_id=f"cid-{legacy_status}",
    )

    status_info = await build_request_service(db).get_request_status(4, request_id)

    assert status_info.status == public_status
    assert status_info.legacy_status == legacy_status
    assert status_info.stage == public_stage
