"""Bookmark-import ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.application.dto.import_bookmarks import BookmarkImportItemResult
    from app.domain.services.import_parsers.base import ImportedBookmark


@runtime_checkable
class BookmarkImportPort(Protocol):
    async def async_import_bookmark(
        self,
        bookmark: ImportedBookmark,
        *,
        user_id: int,
        options: dict[str, Any],
    ) -> BookmarkImportItemResult:
        """Import a single bookmark transactionally."""


@runtime_checkable
class ImportJobRepositoryPort(Protocol):
    """Port for import job tracking operations."""

    async def async_create_job(
        self,
        user_id: int,
        source_format: str,
        file_name: str | None,
        total_items: int,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Insert a new ImportJob and return the created record."""

    async def async_get_job(self, job_id: int) -> dict[str, Any] | None:
        """Return a single import job by ID."""

    async def async_list_jobs(self, user_id: int) -> list[dict[str, Any]]:
        """List user's import jobs, ordered by created_at DESC."""

    async def async_update_progress(
        self,
        job_id: int,
        processed: int,
        created: int,
        skipped: int,
        failed: int,
        errors: list[str] | None = None,
    ) -> None:
        """Update import job progress counters."""

    async def async_set_status(self, job_id: int, status: str) -> None:
        """Update the status field of an import job."""

    async def async_delete_job(self, job_id: int) -> None:
        """Hard delete an import job."""
