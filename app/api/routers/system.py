"""System maintenance endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from starlette.responses import FileResponse

from app.api.models.responses import success_response
from app.api.routers.auth import get_current_user
from app.api.services.auth_service import AuthService
from app.api.services.system_maintenance_service import SystemMaintenanceService
from app.di.api import resolve_api_runtime
from app.di.shared import build_async_audit_sink

router = APIRouter()


def get_system_maintenance_service() -> SystemMaintenanceService:
    """FastAPI dependency provider for maintenance service."""
    return SystemMaintenanceService()


def _extract_user_id(user: dict[str, Any]) -> int:
    raw_user_id = user.get("user_id")
    if isinstance(raw_user_id, bool) or not isinstance(raw_user_id, int):
        raise ValueError("Authenticated user payload is missing integer user_id")
    return raw_user_id


@router.get("/db-dump")
async def download_database(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    service: SystemMaintenanceService = Depends(get_system_maintenance_service),
):
    """
    Download a consistent snapshot of the SQLite database.

    Requires owner permissions.
    """
    await AuthService.require_owner(user)
    user_id = _extract_user_id(user)

    dump_file = service.build_db_dump_file(
        request_headers=request.headers,
        user_id=user_id,
    )

    audit = build_async_audit_sink(resolve_api_runtime(request).db)
    audit("INFO", "admin.db_dump", {"user_id": user_id})

    return FileResponse(
        path=dump_file.path,
        filename=dump_file.filename,
        media_type=dump_file.media_type,
    )


@router.head("/db-dump")
async def head_database(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    service: SystemMaintenanceService = Depends(get_system_maintenance_service),
):
    """HEAD variant for clients that only need headers before downloading."""
    await AuthService.require_owner(user)
    user_id = _extract_user_id(user)

    dump_file = service.build_db_dump_file(
        request_headers=request.headers,
        user_id=user_id,
    )

    audit = build_async_audit_sink(resolve_api_runtime(request).db)
    audit("INFO", "admin.db_dump_head", {"user_id": user_id})

    return FileResponse(
        path=dump_file.path,
        filename=dump_file.filename,
        media_type=dump_file.media_type,
    )


@router.get("/db-info")
async def get_db_info(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    service: SystemMaintenanceService = Depends(get_system_maintenance_service),
):
    """Get database information: table row counts and file size."""
    await AuthService.require_owner(user)
    user_id = _extract_user_id(user)
    audit = build_async_audit_sink(resolve_api_runtime(request).db)
    audit("INFO", "admin.db_info", {"user_id": user_id})
    return success_response(service.get_db_info())


@router.post("/clear-cache")
async def clear_cache(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    service: SystemMaintenanceService = Depends(get_system_maintenance_service),
):
    """Clear Redis URL cache."""
    await AuthService.require_owner(user)
    user_id = _extract_user_id(user)
    cleared = await service.clear_url_cache()
    audit = build_async_audit_sink(resolve_api_runtime(request).db)
    audit("INFO", "admin.clear_cache", {"user_id": user_id, "cleared_keys": cleared})
    return success_response({"cleared_keys": cleared})
