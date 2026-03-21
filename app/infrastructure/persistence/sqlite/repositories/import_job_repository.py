"""SQLite implementation of import job repository.

This adapter handles persistence for bulk import job tracking.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import ImportJob, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository

logger = get_logger(__name__)


class SqliteImportJobRepositoryAdapter(SqliteBaseRepository):
    """Adapter for import job CRUD operations."""

    async def async_create_job(
        self,
        user_id: int,
        source_format: str,
        file_name: str | None,
        total_items: int,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Insert a new ImportJob and return the created record."""

        def _insert() -> dict[str, Any]:
            job = ImportJob.create(
                user=user_id,
                source_format=source_format,
                file_name=file_name,
                total_items=total_items,
                options_json=options or {},
            )
            d = model_to_dict(job)
            assert d is not None
            return d

        return await self._execute(_insert, operation_name="create_import_job")

    async def async_get_job(self, job_id: int) -> dict[str, Any] | None:
        """Return a single import job by ID."""

        def _query() -> dict[str, Any] | None:
            try:
                job = ImportJob.get_by_id(job_id)
            except ImportJob.DoesNotExist:
                return None
            return model_to_dict(job)

        return await self._execute(_query, operation_name="get_import_job", read_only=True)

    async def async_list_jobs(self, user_id: int) -> list[dict[str, Any]]:
        """List user's import jobs, ordered by created_at DESC."""

        def _query() -> list[dict[str, Any]]:
            rows = (
                ImportJob.select()
                .where(ImportJob.user == user_id)
                .order_by(ImportJob.created_at.desc())
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                d = model_to_dict(row)
                if d is not None:
                    result.append(d)
            return result

        return await self._execute(_query, operation_name="list_import_jobs", read_only=True)

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

        def _update() -> None:
            updates = {
                ImportJob.processed_items: processed,
                ImportJob.created_items: created,
                ImportJob.skipped_items: skipped,
                ImportJob.failed_items: failed,
                ImportJob.updated_at: datetime.now(UTC),
            }
            if errors is not None:
                updates[ImportJob.errors_json] = errors
            ImportJob.update(updates).where(ImportJob.id == job_id).execute()

        await self._execute(_update, operation_name="update_import_job_progress")

    async def async_set_status(self, job_id: int, status: str) -> None:
        """Update the status field of an import job."""

        def _update() -> None:
            ImportJob.update(
                {
                    ImportJob.status: status,
                    ImportJob.updated_at: datetime.now(UTC),
                }
            ).where(ImportJob.id == job_id).execute()

        await self._execute(_update, operation_name="set_import_job_status")

    async def async_delete_job(self, job_id: int) -> None:
        """Hard delete an import job."""

        def _delete() -> None:
            ImportJob.delete().where(ImportJob.id == job_id).execute()

        await self._execute(_delete, operation_name="delete_import_job")
