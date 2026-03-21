"""Tests for admin-related Pydantic response models (BackupResponse, ImportJobResponse)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.models.responses import BackupResponse, ImportJobResponse


class TestBackupResponse:
    """Validate BackupResponse serialization and field aliases."""

    def test_full_response(self) -> None:
        resp = BackupResponse(
            id=1,
            type="manual",
            status="completed",
            file_path="/data/backups/1/backup.zip",
            file_size_bytes=1024,
            items_count=42,
            error=None,
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:05:00Z",
        )
        assert resp.id == 1
        assert resp.status == "completed"
        assert resp.items_count == 42

    def test_camel_case_aliases(self) -> None:
        resp = BackupResponse(
            id=1,
            type="manual",
            status="completed",
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:05:00Z",
        )
        dumped = resp.model_dump(by_alias=True)
        assert "filePath" in dumped
        assert "fileSizeBytes" in dumped
        assert "itemsCount" in dumped
        assert "createdAt" in dumped
        assert "updatedAt" in dumped

    def test_optional_fields_default_none(self) -> None:
        resp = BackupResponse(
            id=2,
            type="scheduled",
            status="pending",
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
        )
        assert resp.file_path is None
        assert resp.file_size_bytes is None
        assert resp.items_count is None
        assert resp.error is None

    def test_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            BackupResponse(id=1, type="manual")  # type: ignore[call-arg]


class TestImportJobResponse:
    """Validate ImportJobResponse serialization."""

    def test_full_response(self) -> None:
        resp = ImportJobResponse(
            id=10,
            source_format="netscape_html",
            file_name="bookmarks.html",
            status="completed",
            total_items=100,
            processed_items=100,
            created_items=95,
            skipped_items=3,
            failed_items=2,
            errors=["row 42: invalid URL"],
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:01:00Z",
        )
        assert resp.total_items == 100
        assert resp.created_items == 95
        assert len(resp.errors) == 1

    def test_camel_case_aliases(self) -> None:
        resp = ImportJobResponse(
            id=10,
            source_format="csv",
            status="pending",
            total_items=0,
            processed_items=0,
            created_items=0,
            skipped_items=0,
            failed_items=0,
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
        )
        dumped = resp.model_dump(by_alias=True)
        assert "sourceFormat" in dumped
        assert "totalItems" in dumped
        assert "processedItems" in dumped
        assert "createdItems" in dumped
        assert "skippedItems" in dumped
        assert "failedItems" in dumped

    def test_errors_default_empty(self) -> None:
        resp = ImportJobResponse(
            id=11,
            source_format="pocket",
            status="completed",
            total_items=5,
            processed_items=5,
            created_items=5,
            skipped_items=0,
            failed_items=0,
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
        )
        assert resp.errors == []
