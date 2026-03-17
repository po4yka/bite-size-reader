"""Tests for app/db/video_downloads.py."""

from __future__ import annotations

import logging

from app.db.video_downloads import VideoDownloadManager
from tests.db_helpers import create_request
from tests.integration.helpers import temp_db

logger = logging.getLogger(__name__)


def _make_manager() -> VideoDownloadManager:
    return VideoDownloadManager(logger)


def _make_request_id() -> int:
    return create_request(
        type_="url",
        status="pending",
        correlation_id="test-corr",
        normalized_url="https://example.com",
        dedupe_hash="abc123",
        input_url="https://example.com",
    )


def test_create_and_get_video_download() -> None:
    with temp_db() as _db:
        request_id = _make_request_id()
        mgr = _make_manager()

        download_id = mgr.create_video_download(request_id, "test_video_123")
        assert isinstance(download_id, int)
        assert download_id > 0

        record = mgr.get_video_download_by_request(request_id)
        assert record is not None
        assert record.video_id == "test_video_123"
        assert record.status == "pending"


def test_get_video_download_by_id() -> None:
    with temp_db() as _db:
        request_id = _make_request_id()
        mgr = _make_manager()

        download_id = mgr.create_video_download(request_id, "vid_abc")
        record = mgr.get_video_download_by_id(download_id)
        assert record is not None
        assert record.video_id == "vid_abc"


def test_get_video_download_missing_returns_none() -> None:
    with temp_db() as _db:
        mgr = _make_manager()
        assert mgr.get_video_download_by_request(99999) is None
        assert mgr.get_video_download_by_id(99999) is None


def test_update_video_download_status() -> None:
    with temp_db() as _db:
        request_id = _make_request_id()
        mgr = _make_manager()

        download_id = mgr.create_video_download(request_id, "vid_upd")
        mgr.update_video_download_status(download_id, "completed")

        record = mgr.get_video_download_by_id(download_id)
        assert record.status == "completed"


def test_update_video_download_status_with_error() -> None:
    with temp_db() as _db:
        request_id = _make_request_id()
        mgr = _make_manager()

        download_id = mgr.create_video_download(request_id, "vid_err")
        mgr.update_video_download_status(download_id, "failed", error_text="network error")

        record = mgr.get_video_download_by_id(download_id)
        assert record.status == "failed"
        assert record.error_text == "network error"
