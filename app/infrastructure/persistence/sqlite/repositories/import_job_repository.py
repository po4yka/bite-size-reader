"""SQLAlchemy implementation of the import job repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select, update

from app.db.models import ImportJob, model_to_dict
from app.db.types import _utcnow

if TYPE_CHECKING:
    from app.db.session import Database


class SqliteImportJobRepositoryAdapter:
    """Adapter for import job CRUD operations."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def async_create_job(
        self,
        user_id: int,
        source_format: str,
        file_name: str | None,
        total_items: int,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Insert a new ImportJob and return the created record."""
        async with self._database.transaction() as session:
            job = ImportJob(
                user_id=user_id,
                source_format=source_format,
                file_name=file_name,
                total_items=total_items,
                options_json=options or {},
            )
            session.add(job)
            await session.flush()
            return model_to_dict(job) or {}

    async def async_get_job(self, job_id: int) -> dict[str, Any] | None:
        """Return a single import job by ID."""
        async with self._database.session() as session:
            job = await session.get(ImportJob, job_id)
            return model_to_dict(job)

    async def async_list_jobs(self, user_id: int) -> list[dict[str, Any]]:
        """List user's import jobs, ordered by created_at DESC."""
        async with self._database.session() as session:
            rows = (
                await session.execute(
                    select(ImportJob)
                    .where(ImportJob.user_id == user_id)
                    .order_by(ImportJob.created_at.desc())
                )
            ).scalars()
            return [model_to_dict(row) or {} for row in rows]

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
        updates: dict[str, Any] = {
            "processed_items": processed,
            "created_items": created,
            "skipped_items": skipped,
            "failed_items": failed,
            "updated_at": _utcnow(),
        }
        if errors is not None:
            updates["errors_json"] = errors
        async with self._database.transaction() as session:
            await session.execute(update(ImportJob).where(ImportJob.id == job_id).values(**updates))

    async def async_set_status(self, job_id: int, status: str) -> None:
        """Update the status field of an import job."""
        async with self._database.transaction() as session:
            await session.execute(
                update(ImportJob)
                .where(ImportJob.id == job_id)
                .values(status=status, updated_at=_utcnow())
            )

    async def async_delete_job(self, job_id: int) -> None:
        """Hard delete an import job."""
        async with self._database.transaction() as session:
            await session.execute(delete(ImportJob).where(ImportJob.id == job_id))
