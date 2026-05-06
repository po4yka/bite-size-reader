"""Backup management endpoints."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile
from starlette.responses import FileResponse

from app.api.dependencies.database import (
    get_backup_repository,
    get_session_manager,
    get_user_repository,
)
from app.api.exceptions import APIException, ErrorCode, ResourceNotFoundError
from app.api.models.responses import BackupResponse, success_response
from app.api.routers.auth import get_current_user
from app.api.search_helpers import isotime
from app.core.logging_utils import get_logger
from app.infrastructure.persistence.sqlite.backup_archive_service import (
    async_create_backup_archive,
    async_restore_from_archive,
)

logger = get_logger(__name__)
router = APIRouter()

MAX_BACKUPS_PER_HOUR = 3


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
    backup_repo: Any = Depends(get_backup_repository),
) -> dict[str, Any]:
    """Create a new backup archive. Processing happens in the background."""
    user_id: int = user["user_id"]

    # Rate limit: max N backups per hour
    recent_count = await backup_repo.async_count_recent_backups(user_id, since_hours=1)
    if recent_count >= MAX_BACKUPS_PER_HOUR:
        raise APIException(
            message=f"Rate limit exceeded: maximum {MAX_BACKUPS_PER_HOUR} backups per hour",
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            status_code=429,
        )

    backup = await backup_repo.async_create_backup(user_id, type="manual")
    background_tasks.add_task(
        async_create_backup_archive,
        user_id=user_id,
        backup_id=backup["id"],
        db=get_session_manager(),
    )

    return success_response(_backup_to_response(backup).model_dump(by_alias=True))


@router.get("/")
async def list_backups(
    user: dict[str, Any] = Depends(get_current_user),
    backup_repo: Any = Depends(get_backup_repository),
) -> dict[str, Any]:
    """List user's backups."""
    backups = await backup_repo.async_list_backups(user["user_id"])
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

    summary = await async_restore_from_archive(user["user_id"], content, db=get_session_manager())
    return success_response(summary)


@router.patch("/schedule")
async def update_backup_schedule(
    body: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
    user_repo: Any = Depends(get_user_repository),
) -> dict[str, Any]:
    """Update the user's backup schedule preferences."""
    allowed_keys = {"backup_enabled", "backup_frequency", "backup_retention_count"}
    update_data = {k: v for k, v in body.items() if k in allowed_keys}
    if not update_data:
        raise APIException(
            message="No valid schedule fields provided. "
            "Allowed: backup_enabled, backup_frequency, backup_retention_count",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    user_record, _ = await user_repo.async_get_or_create_user(
        user["user_id"],
        username=user.get("username"),
        is_owner=False,
    )
    prefs = user_record.get("preferences_json") or {}
    prefs.update(update_data)
    await user_repo.async_update_user_preferences(user["user_id"], prefs)
    result = {key: prefs.get(key) for key in allowed_keys}
    return success_response({"schedule": result})


@router.get("/schedule")
async def get_backup_schedule(
    user: dict[str, Any] = Depends(get_current_user),
    user_repo: Any = Depends(get_user_repository),
) -> dict[str, Any]:
    """Read the user's backup schedule preferences."""
    allowed_keys = {"backup_enabled", "backup_frequency", "backup_retention_count"}
    user_record = await user_repo.async_get_user_by_telegram_id(user["user_id"])
    prefs = user_record.get("preferences_json") if user_record else {}
    if not isinstance(prefs, dict):
        prefs = {}
    result = {key: prefs.get(key) for key in allowed_keys}
    return success_response({"schedule": result})


# ---------------------------------------------------------------------------
# Parameterized routes (/{backup_id})
# ---------------------------------------------------------------------------


@router.get("/{backup_id}")
async def get_backup(
    backup_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    backup_repo: Any = Depends(get_backup_repository),
) -> dict[str, Any]:
    """Get backup details."""
    backup = await _verify_ownership(backup_repo, backup_id, user["user_id"])
    return success_response(_backup_to_response(backup).model_dump(by_alias=True))


@router.get("/{backup_id}/download")
async def download_backup(
    backup_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    backup_repo: Any = Depends(get_backup_repository),
) -> FileResponse:
    """Download the backup ZIP file."""
    backup = await _verify_ownership(backup_repo, backup_id, user["user_id"])

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
    backup_repo: Any = Depends(get_backup_repository),
) -> dict[str, Any]:
    """Delete a backup record and its file from disk."""
    backup = await _verify_ownership(backup_repo, backup_id, user["user_id"])

    # Remove file from disk
    file_path = backup.get("file_path")
    if file_path and os.path.isfile(file_path):
        os.remove(file_path)

    await backup_repo.async_delete_backup(backup_id)
    return success_response({"deleted": True, "id": backup_id})
