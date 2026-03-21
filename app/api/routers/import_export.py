"""Import/Export endpoints for bookmark data."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from starlette.responses import StreamingResponse

from app.api.exceptions import APIException, ErrorCode, ResourceNotFoundError
from app.api.models.responses import ImportJobResponse, success_response
from app.api.routers.auth import get_current_user
from app.api.search_helpers import isotime
from app.application.dto.import_bookmarks import ImportBookmarksCommand
from app.application.use_cases.import_pipeline import ImportBookmarksUseCase
from app.core.logging_utils import get_logger
from app.domain.services.import_export import (
    CsvExporter,
    FormatDetector,
    JsonExporter,
    NetscapeHtmlExporter,
)
from app.domain.services.import_parsers import PARSER_REGISTRY

logger = get_logger(__name__)
router = APIRouter()
_background_import_tasks: set[asyncio.Task[None]] = set()

_EXPORT_FORMAT_MAP: dict[str, tuple[type, str, str]] = {
    "json": (JsonExporter, "application/json", "bookmarks.json"),
    "csv": (CsvExporter, "text/csv", "bookmarks.csv"),
    "html": (NetscapeHtmlExporter, "text/html", "bookmarks.html"),
}


def _get_import_job_repo():
    """Lazily import and build the import job repository adapter."""
    from app.di.api import get_current_api_runtime

    runtime = get_current_api_runtime()
    from app.infrastructure.persistence.sqlite.repositories.import_job_repository import (
        SqliteImportJobRepositoryAdapter,
    )

    return SqliteImportJobRepositoryAdapter(runtime.db)


def _job_to_response(job: dict[str, Any]) -> ImportJobResponse:
    """Convert a job dict to a response model."""
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


async def _verify_job_ownership(repo: Any, job_id: int, user_id: int) -> dict[str, Any]:
    """Verify the import job exists and belongs to the user."""
    job = await repo.async_get_job(job_id)
    if job is None:
        raise ResourceNotFoundError("ImportJob", job_id)
    if job["user"] != user_id:
        raise ResourceNotFoundError("ImportJob", job_id)
    return job


async def _process_import(
    repo: Any,
    job_id: int,
    bookmarks: list[Any],
    options: dict[str, Any],
    user_id: int,
) -> None:
    """Background task: process parsed bookmarks and update job progress."""
    from app.di.api import get_current_api_runtime
    from app.infrastructure.persistence.sqlite.repositories.bookmark_import_repository import (
        SqliteBookmarkImportAdapter,
    )

    runtime = get_current_api_runtime()
    use_case = ImportBookmarksUseCase(
        import_job_repository=repo,
        bookmark_import_repository=SqliteBookmarkImportAdapter(runtime.db),
    )
    try:
        await use_case.execute(
            ImportBookmarksCommand(
                job_id=job_id,
                bookmarks=bookmarks,
                user_id=user_id,
                options=options,
            )
        )
    except Exception as exc:
        logger.error("import_processing_failed", extra={"job_id": job_id, "error": str(exc)})


# ---------------------------------------------------------------------------
# Import endpoints
# ---------------------------------------------------------------------------


@router.post("/import", status_code=201)
async def import_bookmarks(
    file: UploadFile = File(...),
    options: str = Form(default="{}"),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Import bookmarks from an uploaded file."""
    # Parse options
    try:
        opts = json.loads(options)
    except (json.JSONDecodeError, TypeError) as err:
        raise APIException(
            message="Invalid JSON in options field",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        ) from err

    # Read file content
    content = await file.read()
    if not content:
        raise APIException(
            message="Uploaded file is empty",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    # Detect format
    filename = file.filename or "unknown"
    source_format = FormatDetector.detect(filename, content)
    if source_format == "unknown" or source_format not in PARSER_REGISTRY:
        raise APIException(
            message=f"Unrecognized import format for file: {filename}",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    # Parse bookmarks
    parser_cls = PARSER_REGISTRY[source_format]
    parser = parser_cls()
    bookmarks = parser.parse(content)

    if not bookmarks:
        raise APIException(
            message="No bookmarks found in uploaded file",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    # Create import job
    repo = _get_import_job_repo()
    job = await repo.async_create_job(
        user_id=user["user_id"],
        source_format=source_format,
        file_name=filename,
        total_items=len(bookmarks),
        options=opts,
    )

    # Kick off background processing -- store reference to prevent GC
    task = asyncio.create_task(_process_import(repo, job["id"], bookmarks, opts, user["user_id"]))
    _background_import_tasks.add(task)
    task.add_done_callback(_background_import_tasks.discard)

    return success_response(_job_to_response(job).model_dump(by_alias=True))


@router.get("/import/{job_id}")
async def get_import_job(
    job_id: int,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get import job status and progress."""
    repo = _get_import_job_repo()
    job = await _verify_job_ownership(repo, job_id, user["user_id"])
    return success_response(_job_to_response(job).model_dump(by_alias=True))


@router.get("/import")
async def list_import_jobs(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List user's import jobs."""
    repo = _get_import_job_repo()
    jobs = await repo.async_list_jobs(user["user_id"])
    items = [_job_to_response(j).model_dump(by_alias=True) for j in jobs]
    return success_response({"jobs": items})


@router.delete("/import/{job_id}")
async def delete_import_job(
    job_id: int,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete an import job."""
    repo = _get_import_job_repo()
    await _verify_job_ownership(repo, job_id, user["user_id"])
    await repo.async_delete_job(job_id)
    return success_response({"deleted": True, "id": job_id})


# ---------------------------------------------------------------------------
# Export endpoint
# ---------------------------------------------------------------------------


@router.get("/export")
async def export_bookmarks(
    format: str = Query(default="json", pattern="^(json|csv|html)$"),
    tag: str | None = Query(default=None),
    collection_id: int | None = Query(default=None),
    user: dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    """Export user summaries in the requested format."""
    from app.db.models import (
        Collection,
        CollectionItem,
        Request,
        Summary,
        SummaryTag,
        Tag,
        model_to_dict,
    )
    from app.di.api import get_current_api_runtime

    runtime = get_current_api_runtime()

    def _query_summaries() -> list[dict[str, Any]]:
        user_id = user["user_id"]
        query = (
            Summary.select(Summary, Request)
            .join(Request, on=(Summary.request == Request.id))
            .where(
                (Request.user == user_id) & (Summary.is_deleted == False)  # noqa: E712
            )
        )

        # Apply tag filter
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
                    st.summary_id
                    for st in SummaryTag.select(SummaryTag.summary).where(
                        SummaryTag.tag == tag_obj.id
                    )
                ]
                query = query.where(Summary.id.in_(tagged_summary_ids))
            else:
                return []

        # Apply collection filter
        if collection_id is not None:
            collection_summary_ids = [
                ci.summary_id
                for ci in CollectionItem.select(CollectionItem.summary).where(
                    CollectionItem.collection == collection_id
                )
            ]
            query = query.where(Summary.id.in_(collection_summary_ids))

        summaries: list[dict[str, Any]] = []
        for row in query:
            d = model_to_dict(row)
            if d is None:
                continue

            # Attach URL and title from request
            req = row.request
            d["url"] = req.input_url or req.normalized_url or ""
            d["title"] = ""
            json_payload = d.get("json_payload")
            if isinstance(json_payload, dict):
                d["title"] = json_payload.get("title", "")

            # Attach tags
            tag_rows = (
                Tag.select(Tag.name)
                .join(SummaryTag, on=(SummaryTag.tag == Tag.id))
                .where(
                    (SummaryTag.summary == row.id) & (Tag.is_deleted == False)  # noqa: E712
                )
            )
            d["tags"] = [{"name": t.name} for t in tag_rows]

            # Attach collections
            coll_rows = (
                Collection.select(Collection.name)
                .join(CollectionItem, on=(CollectionItem.collection == Collection.id))
                .where(
                    (CollectionItem.summary == row.id) & (Collection.is_deleted == False)  # noqa: E712
                )
            )
            d["collections"] = [{"name": c.name} for c in coll_rows]

            summaries.append(d)

        return summaries

    summaries = await runtime.db.async_execute(
        _query_summaries, operation_name="export_query", read_only=True
    )

    exporter_cls, content_type, filename = _EXPORT_FORMAT_MAP[format]
    exporter = exporter_cls()
    body = exporter.serialize(summaries)

    return StreamingResponse(
        iter([body]),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
