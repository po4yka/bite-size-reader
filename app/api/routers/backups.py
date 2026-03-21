"""Backup management endpoints."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile
from starlette.responses import FileResponse

from app.api.exceptions import APIException, ErrorCode, ResourceNotFoundError
from app.api.models.responses import BackupResponse, success_response
from app.api.routers.auth import get_current_user
from app.api.search_helpers import isotime
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC

logger = get_logger(__name__)
router = APIRouter()

MAX_BACKUPS_PER_HOUR = 3


def _get_backup_repo():
    """Lazily import and build the backup repository adapter."""
    from app.di.api import get_current_api_runtime

    runtime = get_current_api_runtime()
    from app.infrastructure.persistence.sqlite.repositories.backup_repository import (
        SqliteBackupRepositoryAdapter,
    )

    return SqliteBackupRepositoryAdapter(runtime.db)


def _get_data_dir() -> str:
    """Resolve the data directory from the DB path."""
    from app.di.api import get_current_api_runtime

    runtime = get_current_api_runtime()
    return str(os.path.dirname(runtime.db.path))


def _backup_to_response(b: dict[str, Any]) -> BackupResponse:
    """Convert a backup dict to a response model."""
    return BackupResponse(
        id=b["id"],
        type=b["type"],
        status=b["status"],
        file_path=b.get("file_path"),
        file_size_bytes=b.get("file_size_bytes"),
        items_count=b.get("items_count"),
        error=b.get("error"),
        created_at=isotime(b["created_at"]),
        updated_at=isotime(b["updated_at"]),
    )


async def _verify_ownership(repo: Any, backup_id: int, user_id: int) -> dict[str, Any]:
    """Verify the backup exists and belongs to the user."""
    backup = await repo.async_get_backup(backup_id)
    if backup is None:
        raise ResourceNotFoundError("Backup", backup_id)
    if backup["user"] != user_id:
        raise ResourceNotFoundError("Backup", backup_id)
    return backup


# ---------------------------------------------------------------------------
# Fixed-path routes (must come before /{backup_id} to avoid path conflicts)
# ---------------------------------------------------------------------------


@router.post("/", status_code=201)
async def create_backup(
    background_tasks: BackgroundTasks,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new backup archive. Processing happens in the background."""
    repo = _get_backup_repo()
    user_id: int = user["user_id"]

    # Rate limit: max N backups per hour
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    recent_count = await repo.async_count_recent_backups(user_id, one_hour_ago)
    if recent_count >= MAX_BACKUPS_PER_HOUR:
        raise APIException(
            message=f"Rate limit exceeded: maximum {MAX_BACKUPS_PER_HOUR} backups per hour",
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            status_code=429,
        )

    backup = await repo.async_create_backup(user_id, type="manual")
    data_dir = _get_data_dir()

    from app.domain.services.backup_service import create_backup_archive

    background_tasks.add_task(create_backup_archive, user_id, backup["id"], data_dir)

    return success_response(_backup_to_response(backup).model_dump(by_alias=True))


@router.get("/")
async def list_backups(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List user's backups."""
    repo = _get_backup_repo()
    backups = await repo.async_list_backups(user["user_id"])
    items = [_backup_to_response(b).model_dump(by_alias=True) for b in backups]
    return success_response({"backups": items})


@router.post("/restore")
async def restore_backup(
    file: UploadFile,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Restore user data from an uploaded backup ZIP."""
    content = await file.read()
    if not content:
        raise APIException(
            message="Uploaded file is empty",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    from app.domain.services.backup_service import restore_from_archive

    summary = restore_from_archive(user["user_id"], content)
    return success_response(summary)


@router.patch("/schedule")
async def update_backup_schedule(
    body: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Update the user's backup schedule preferences."""
    from app.db.models import User
    from app.di.api import get_current_api_runtime

    runtime = get_current_api_runtime()

    allowed_keys = {"backup_enabled", "backup_frequency", "backup_retention_count"}
    update_data = {k: v for k, v in body.items() if k in allowed_keys}
    if not update_data:
        raise APIException(
            message="No valid schedule fields provided. "
            "Allowed: backup_enabled, backup_frequency, backup_retention_count",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    def _update_prefs() -> dict[str, Any]:
        user_row = User.get_by_id(user["user_id"])
        prefs = user_row.preferences_json or {}
        prefs.update(update_data)
        user_row.preferences_json = prefs
        user_row.save()
        return {k: prefs.get(k) for k in allowed_keys}

    result = await runtime.db.async_execute(_update_prefs, operation_name="update_backup_schedule")
    return success_response({"schedule": result})


@router.get("/schedule")
async def get_backup_schedule(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Read the user's backup schedule preferences."""
    from app.db.models import User
    from app.di.api import get_current_api_runtime

    runtime = get_current_api_runtime()

    allowed_keys = {"backup_enabled", "backup_frequency", "backup_retention_count"}

    def _read_prefs() -> dict[str, Any]:
        user_row = User.get_by_id(user["user_id"])
        prefs = user_row.preferences_json or {}
        return {k: prefs.get(k) for k in allowed_keys}

    result = await runtime.db.async_execute(
        _read_prefs, operation_name="get_backup_schedule", read_only=True
    )
    return success_response({"schedule": result})


# ---------------------------------------------------------------------------
# Parameterized routes (/{backup_id})
# ---------------------------------------------------------------------------


@router.get("/{backup_id}")
async def get_backup(
    backup_id: int,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get backup details."""
    repo = _get_backup_repo()
    backup = await _verify_ownership(repo, backup_id, user["user_id"])
    return success_response(_backup_to_response(backup).model_dump(by_alias=True))


@router.get("/{backup_id}/download")
async def download_backup(
    backup_id: int,
    user: dict[str, Any] = Depends(get_current_user),
) -> FileResponse:
    """Download the backup ZIP file."""
    repo = _get_backup_repo()
    backup = await _verify_ownership(repo, backup_id, user["user_id"])

    if backup["status"] != "completed":
        raise APIException(
            message="Backup is not yet completed",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    file_path = backup.get("file_path")
    if not file_path or not os.path.isfile(file_path):
        raise APIException(
            message="Backup file not found on disk",
            error_code=ErrorCode.NOT_FOUND,
            status_code=404,
        )

    filename = os.path.basename(file_path)
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/zip",
    )


@router.delete("/{backup_id}")
async def delete_backup(
    backup_id: int,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete a backup record and its file from disk."""
    repo = _get_backup_repo()
    backup = await _verify_ownership(repo, backup_id, user["user_id"])

    # Remove file from disk
    file_path = backup.get("file_path")
    if file_path and os.path.isfile(file_path):
        os.remove(file_path)

    await repo.async_delete_backup(backup_id)
    return success_response({"deleted": True, "id": backup_id})
