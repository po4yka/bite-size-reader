"""Admin read-only endpoints for system monitoring."""

from __future__ import annotations

import contextlib
import datetime as _dt
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies.database import get_session_manager
from app.api.models.responses import success_response
from app.api.routers.auth import get_current_user
from app.api.services.admin_read_service import AdminReadService
from app.api.services.auth_service import AuthService
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.di.shared import build_async_audit_sink

router = APIRouter()
logger = get_logger(__name__)


def _resolve_db(request: Any) -> Any:
    """Resolve DB handle for audit sinks, falling back to session manager."""
    from app.di.api import resolve_api_runtime

    with contextlib.suppress(RuntimeError):
        return resolve_api_runtime(request).db
    return get_session_manager(request)


def _extract_user_id(user: dict[str, Any]) -> int:
    raw_user_id = user.get("user_id")
    if isinstance(raw_user_id, bool) or not isinstance(raw_user_id, int):
        raise ValueError("Authenticated user payload is missing integer user_id")
    return raw_user_id


def _seven_days_ago() -> _dt.datetime:
    return _dt.datetime.now(UTC) - _dt.timedelta(days=7)


def _today_start() -> _dt.datetime:
    return _dt.datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# 1. GET /users -- List all users with stats
# ---------------------------------------------------------------------------


@router.get("/users")
async def list_users(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
):
    """List all users with per-user summary/request/tag/collection counts."""
    await AuthService.require_owner(user)
    user_id = _extract_user_id(user)

    audit = build_async_audit_sink(_resolve_db(request))
    audit("INFO", "admin.list_users", {"user_id": user_id})
    return success_response(await AdminReadService(_resolve_db(request)).list_users())


# ---------------------------------------------------------------------------
# 2. GET /jobs -- Background job status
# ---------------------------------------------------------------------------


@router.get("/jobs")
async def job_status(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Pipeline and import job status overview."""
    await AuthService.require_owner(user)
    user_id = _extract_user_id(user)

    audit = build_async_audit_sink(_resolve_db(request))
    audit("INFO", "admin.job_status", {"user_id": user_id})
    service = AdminReadService(_resolve_db(request))
    return success_response(await service.job_status(today=_today_start()))


# ---------------------------------------------------------------------------
# 3. GET /health/content -- Content health report
# ---------------------------------------------------------------------------


@router.get("/health/content")
async def content_health(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Content pipeline health: totals, failure breakdown, recent errors."""
    await AuthService.require_owner(user)
    user_id = _extract_user_id(user)

    audit = build_async_audit_sink(_resolve_db(request))
    audit("INFO", "admin.content_health", {"user_id": user_id})
    return success_response(await AdminReadService(_resolve_db(request)).content_health())


# ---------------------------------------------------------------------------
# 4. GET /metrics -- System metrics
# ---------------------------------------------------------------------------


@router.get("/metrics")
async def system_metrics(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Database, LLM, and scraper metrics."""
    await AuthService.require_owner(user)
    user_id = _extract_user_id(user)

    audit = build_async_audit_sink(_resolve_db(request))
    audit("INFO", "admin.metrics", {"user_id": user_id})
    service = AdminReadService(_resolve_db(request))
    return success_response(await service.system_metrics(since=_seven_days_ago()))


# ---------------------------------------------------------------------------
# 5. GET /audit-log -- Paginated audit log
# ---------------------------------------------------------------------------


@router.get("/audit-log")
async def audit_log(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    action: str | None = Query(None, description="Filter by event name"),
    user_id_filter: int | None = Query(
        None, alias="user_id", description="Filter by user_id in details"
    ),
    since: str | None = Query(None, description="ISO datetime lower bound"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Paginated, filterable audit log."""
    await AuthService.require_owner(user)
    caller_id = _extract_user_id(user)

    audit = build_async_audit_sink(_resolve_db(request))
    audit("INFO", "admin.audit_log", {"user_id": caller_id})
    service = AdminReadService(_resolve_db(request))
    return success_response(
        await service.audit_log(
            action=action,
            user_id_filter=user_id_filter,
            since=since,
            limit=limit,
            offset=offset,
        )
    )
