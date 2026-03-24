"""Import/Export endpoints for bookmark data."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from starlette.responses import StreamingResponse

from app.api.exceptions import APIException, ErrorCode
from app.api.models.responses import success_response
from app.api.routers.auth import get_current_user
from app.api.services.import_export_service import ImportExportService
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


async def _run_import_task(
    service: ImportExportService,
    *,
    job_id: int,
    bookmarks: list[Any],
    options: dict[str, Any],
    user_id: int,
) -> None:
    """Execute bookmark import in the background and log failures."""
    try:
        await service.process_import(
            job_id=job_id,
            bookmarks=bookmarks,
            options=options,
            user_id=user_id,
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

    service = ImportExportService()
    job = await service.create_import_job(
        user_id=user["user_id"],
        source_format=source_format,
        file_name=filename,
        total_items=len(bookmarks),
        options=opts,
    )

    # Kick off background processing -- store reference to prevent GC
    task = asyncio.create_task(
        _run_import_task(
            service,
            job_id=job["id"],
            bookmarks=bookmarks,
            options=opts,
            user_id=user["user_id"],
        )
    )
    _background_import_tasks.add(task)
    task.add_done_callback(_background_import_tasks.discard)

    return success_response(job)


@router.get("/import/{job_id}")
async def get_import_job(
    job_id: int,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get import job status and progress."""
    job = await ImportExportService().get_import_job(job_id=job_id, user_id=user["user_id"])
    return success_response(job)


@router.get("/import")
async def list_import_jobs(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List user's import jobs."""
    jobs = await ImportExportService().list_import_jobs(user_id=user["user_id"])
    return success_response({"jobs": jobs})


@router.delete("/import/{job_id}")
async def delete_import_job(
    job_id: int,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete an import job."""
    await ImportExportService().delete_import_job(job_id=job_id, user_id=user["user_id"])
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
    summaries = await ImportExportService().export_summaries(
        user_id=user["user_id"],
        tag=tag,
        collection_id=collection_id,
    )

    exporter_cls, content_type, filename = _EXPORT_FORMAT_MAP[format]
    exporter = exporter_cls()
    body = exporter.serialize(summaries)

    return StreamingResponse(
        iter([body]),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
