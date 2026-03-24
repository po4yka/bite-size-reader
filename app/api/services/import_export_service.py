"""Service logic for import/export API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.api.dependencies.database import (
    get_bookmark_import_repository,
    get_import_job_repository,
    get_session_manager,
)
from app.api.exceptions import ResourceNotFoundError
from app.api.models.responses import ImportJobResponse
from app.api.search_helpers import isotime
from app.application.dto.import_bookmarks import ImportBookmarksCommand
from app.application.use_cases.import_pipeline import ImportBookmarksUseCase

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager


class ImportExportService:
    """Owns import job tracking and export dataset assembly."""

    def __init__(self, session_manager: DatabaseSessionManager | None = None) -> None:
        self._db = session_manager or get_session_manager()
        self._import_job_repo = get_import_job_repository(self._db)
        self._bookmark_import_repo = get_bookmark_import_repository(self._db)

    async def create_import_job(
        self,
        *,
        user_id: int,
        source_format: str,
        file_name: str | None,
        total_items: int,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        job = await self._import_job_repo.async_create_job(
            user_id=user_id,
            source_format=source_format,
            file_name=file_name,
            total_items=total_items,
            options=options,
        )
        return self._job_to_response(job).model_dump(by_alias=True)

    async def process_import(
        self,
        *,
        job_id: int,
        bookmarks: list[Any],
        options: dict[str, Any],
        user_id: int,
    ) -> None:
        use_case = ImportBookmarksUseCase(
            import_job_repository=self._import_job_repo,
            bookmark_import_repository=self._bookmark_import_repo,
        )
        await use_case.execute(
            ImportBookmarksCommand(
                job_id=job_id,
                bookmarks=bookmarks,
                user_id=user_id,
                options=options,
            )
        )

    async def get_import_job(self, *, job_id: int, user_id: int) -> dict[str, Any]:
        job = await self._verify_job_ownership(job_id=job_id, user_id=user_id)
        return self._job_to_response(job).model_dump(by_alias=True)

    async def list_import_jobs(self, *, user_id: int) -> list[dict[str, Any]]:
        jobs = await self._import_job_repo.async_list_jobs(user_id)
        return [self._job_to_response(job).model_dump(by_alias=True) for job in jobs]

    async def delete_import_job(self, *, job_id: int, user_id: int) -> None:
        await self._verify_job_ownership(job_id=job_id, user_id=user_id)
        await self._import_job_repo.async_delete_job(job_id)

    async def export_summaries(
        self,
        *,
        user_id: int,
        tag: str | None,
        collection_id: int | None,
    ) -> list[dict[str, Any]]:
        """Return serialized summary rows for bookmark export."""

        def _query() -> list[dict[str, Any]]:
            from app.db.models import (
                Collection,
                CollectionItem,
                Request,
                Summary,
                SummaryTag,
                Tag,
                model_to_dict,
            )

            query = (
                Summary.select(Summary, Request)
                .join(Request, on=(Summary.request == Request.id))
                .where(
                    (Request.user == user_id) & (Summary.is_deleted == False)  # noqa: E712
                )
            )

            if tag:
                tag_obj = (
                    Tag.select()
                    .where(
                        (Tag.user == user_id) & (Tag.name == tag) & (Tag.is_deleted == False)  # noqa: E712
                    )
                    .first()
                )
                if tag_obj:
                    tagged_summary_ids = [
                        summary_tag.summary_id
                        for summary_tag in SummaryTag.select(SummaryTag.summary).where(
                            SummaryTag.tag == tag_obj.id
                        )
                    ]
                    query = query.where(Summary.id.in_(tagged_summary_ids))
                else:
                    return []

            if collection_id is not None:
                collection_summary_ids = [
                    item.summary_id
                    for item in CollectionItem.select(CollectionItem.summary).where(
                        CollectionItem.collection == collection_id
                    )
                ]
                query = query.where(Summary.id.in_(collection_summary_ids))

            summaries: list[dict[str, Any]] = []
            for row in query:
                summary_dict = model_to_dict(row)
                if summary_dict is None:
                    continue

                req = row.request
                summary_dict["url"] = req.input_url or req.normalized_url or ""
                summary_dict["title"] = ""
                json_payload = summary_dict.get("json_payload")
                if isinstance(json_payload, dict):
                    summary_dict["title"] = json_payload.get("title", "")

                tag_rows = (
                    Tag.select(Tag.name)
                    .join(SummaryTag, on=(SummaryTag.tag == Tag.id))
                    .where(
                        (SummaryTag.summary == row.id) & (Tag.is_deleted == False)  # noqa: E712
                    )
                )
                summary_dict["tags"] = [{"name": tag_row.name} for tag_row in tag_rows]

                collection_rows = (
                    Collection.select(Collection.name)
                    .join(CollectionItem, on=(CollectionItem.collection == Collection.id))
                    .where(
                        (CollectionItem.summary == row.id) & (Collection.is_deleted == False)  # noqa: E712
                    )
                )
                summary_dict["collections"] = [
                    {"name": collection.name} for collection in collection_rows
                ]
                summaries.append(summary_dict)

            return summaries

        return await self._db.async_execute(_query, operation_name="export_query", read_only=True)

    async def _verify_job_ownership(self, *, job_id: int, user_id: int) -> dict[str, Any]:
        job = await self._import_job_repo.async_get_job(job_id)
        if job is None:
            raise ResourceNotFoundError("ImportJob", job_id)
        if job["user"] != user_id:
            raise ResourceNotFoundError("ImportJob", job_id)
        return job

    @staticmethod
    def _job_to_response(job: dict[str, Any]) -> ImportJobResponse:
        return ImportJobResponse(
            id=job["id"],
            source_format=job["source_format"],
            file_name=job.get("file_name"),
            status=job["status"],
            total_items=job["total_items"],
            processed_items=job["processed_items"],
            created_items=job["created_items"],
            skipped_items=job["skipped_items"],
            failed_items=job["failed_items"],
            errors=job.get("errors_json") or [],
            created_at=isotime(job["created_at"]),
            updated_at=isotime(job["updated_at"]),
        )
