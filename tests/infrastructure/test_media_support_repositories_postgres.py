"""Postgres-backed tests for small media/support repositories."""

from __future__ import annotations

import datetime as dt
import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, select

from app.config.database import DatabaseConfig
from app.core.time_utils import UTC
from app.db.models import AttachmentProcessing, AuditLog, Request, VideoDownload
from app.db.session import Database
from app.infrastructure.persistence.repositories.attachment_processing_repository import (
    AttachmentProcessingRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.audit_log_repository import (
    AuditLogRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.video_download_repository import (
    VideoDownloadRepositoryAdapter,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def _test_dsn() -> str:
    return os.getenv("TEST_DATABASE_URL", "")


@pytest.fixture
async def database() -> AsyncGenerator[Database]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for Postgres repository tests")

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
        await session.execute(delete(AttachmentProcessing))
        await session.execute(delete(VideoDownload))
        await session.execute(delete(AuditLog))
        await session.execute(delete(Request))


async def _request(database: Database, *, suffix: str) -> Request:
    async with database.transaction() as session:
        request = Request(
            type="url",
            status="pending",
            correlation_id=f"support-{suffix}",
            user_id=9009,
            input_url=f"https://example.com/{suffix}",
            normalized_url=f"https://example.com/{suffix}",
            dedupe_hash=f"support-{suffix}",
        )
        session.add(request)
        await session.flush()
        return request


@pytest.mark.asyncio
async def test_audit_log_repository_inserts_json(database: Database) -> None:
    repo = AuditLogRepositoryAdapter(database)

    log_id = await repo.async_insert_audit_log("info", "login", {"ok": True})

    async with database.session() as session:
        row = await session.get(AuditLog, log_id)
    assert row is not None
    assert row.level == "info"
    assert row.event == "login"
    assert row.details_json == {"ok": True}


@pytest.mark.asyncio
async def test_attachment_processing_repository_creates_and_updates(database: Database) -> None:
    repo = AttachmentProcessingRepositoryAdapter(database)
    request = await _request(database, suffix="attachment")

    await repo.async_create_processing(
        request_id=request.id,
        file_type="pdf",
        mime_type="application/pdf",
        file_name="paper.pdf",
        file_size_bytes=1234,
        status="processing",
    )
    assert await repo.async_update_processing(
        request.id,
        status="completed",
        extracted_text_length=42,
        ignored_field="ignored",
    )
    assert await repo.async_update_processing(999999, status="missing") is False

    async with database.session() as session:
        row = await session.scalar(
            select(AttachmentProcessing).where(AttachmentProcessing.request_id == request.id)
        )
    assert row is not None
    assert row.status == "completed"
    assert row.extracted_text_length == 42


@pytest.mark.asyncio
async def test_video_download_repository_creates_reads_and_updates(database: Database) -> None:
    repo = VideoDownloadRepositoryAdapter(database)
    request = await _request(database, suffix="video")

    download_id = await repo.async_create_video_download(request.id, "yt-1")
    started_at = dt.datetime.now(UTC)
    await repo.async_update_video_download_status(
        download_id,
        "downloading",
        download_started_at=started_at,
    )
    await repo.async_update_video_download(
        download_id,
        title="Video",
        duration_sec=12,
        unknown_field="ignored",
    )

    by_id = await repo.async_get_video_download_by_id(download_id)
    by_request = await repo.async_get_video_download_by_request(request.id)
    assert by_id is not None
    assert by_request is not None
    assert by_id["id"] == by_request["id"] == download_id
    assert by_id["status"] == "downloading"
    assert by_id["title"] == "Video"
    assert by_id["duration_sec"] == 12
