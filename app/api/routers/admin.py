"""Admin read-only endpoints for system monitoring."""

from __future__ import annotations

import contextlib
import datetime as _dt
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from peewee import fn

from app.api.dependencies.database import get_session_manager
from app.api.models.responses import success_response
from app.api.routers.auth import get_current_user
from app.api.search_helpers import isotime
from app.api.services.auth_service import AuthService
from app.api.services.system_maintenance_service import SystemMaintenanceService
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import (
    AuditLog,
    Collection,
    CrawlResult,
    ImportJob,
    LLMCall,
    Request as RequestModel,
    Summary,
    Tag,
    User,
)
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


def get_system_maintenance_service() -> SystemMaintenanceService:
    """FastAPI dependency provider for maintenance service."""
    return SystemMaintenanceService()


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

    users_list: list[dict[str, Any]] = []
    for u in User.select():
        uid = u.telegram_user_id

        summary_count = (
            Summary.select()
            .join(RequestModel, on=(Summary.request == RequestModel.id))
            .where(RequestModel.user_id == uid)
            .count()
        )
        request_count = RequestModel.select().where(RequestModel.user_id == uid).count()
        tag_count = Tag.select().where(Tag.user == uid).count()
        collection_count = Collection.select().where(Collection.user == uid).count()

        users_list.append(
            {
                "user_id": uid,
                "username": u.username,
                "is_owner": u.is_owner,
                "summary_count": summary_count,
                "request_count": request_count,
                "tag_count": tag_count,
                "collection_count": collection_count,
                "created_at": isotime(u.created_at),
            }
        )

    return success_response({"users": users_list, "total_users": len(users_list)})


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

    today = _today_start()

    pending = RequestModel.select().where(RequestModel.status == "pending").count()
    processing = (
        RequestModel.select()
        .where(RequestModel.status.in_(["crawling", "summarizing", "processing"]))
        .count()
    )
    completed_today = (
        RequestModel.select()
        .where((RequestModel.status == "completed") & (RequestModel.updated_at >= today))
        .count()
    )
    failed_today = (
        RequestModel.select()
        .where((RequestModel.status == "error") & (RequestModel.updated_at >= today))
        .count()
    )

    imports_active = ImportJob.select().where(ImportJob.status == "processing").count()
    imports_completed_today = (
        ImportJob.select()
        .where((ImportJob.status == "completed") & (ImportJob.updated_at >= today))
        .count()
    )

    return success_response(
        {
            "pipeline": {
                "pending": pending,
                "processing": processing,
                "completed_today": completed_today,
                "failed_today": failed_today,
            },
            "imports": {
                "active": imports_active,
                "completed_today": imports_completed_today,
            },
        }
    )


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

    total_summaries = Summary.select().count()
    total_requests = RequestModel.select().count()
    failed_requests = RequestModel.select().where(RequestModel.status == "error").count()

    # Group failures by error_type
    failed_by_error_type: dict[str, int] = {}
    error_groups = (
        RequestModel.select(RequestModel.error_type, fn.COUNT(RequestModel.id).alias("cnt"))
        .where(RequestModel.status == "error")
        .group_by(RequestModel.error_type)
    )
    for row in error_groups:
        key = row.error_type or "unknown"
        failed_by_error_type[key] = row.cnt

    # Recent 20 failures
    recent_failures: list[dict[str, Any]] = []
    for r in (
        RequestModel.select()
        .where(RequestModel.status == "error")
        .order_by(RequestModel.created_at.desc())
        .limit(20)
    ):
        recent_failures.append(
            {
                "id": r.id,
                "url": r.input_url,
                "error_type": r.error_type,
                "error_message": r.error_message,
                "created_at": isotime(r.created_at),
            }
        )

    return success_response(
        {
            "total_summaries": total_summaries,
            "total_requests": total_requests,
            "failed_requests": failed_requests,
            "failed_by_error_type": failed_by_error_type,
            "recent_failures": recent_failures,
        }
    )


# ---------------------------------------------------------------------------
# 4. GET /metrics -- System metrics
# ---------------------------------------------------------------------------


@router.get("/metrics")
async def system_metrics(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    service: SystemMaintenanceService = Depends(get_system_maintenance_service),
):
    """Database, LLM, and scraper metrics."""
    await AuthService.require_owner(user)
    user_id = _extract_user_id(user)

    audit = build_async_audit_sink(_resolve_db(request))
    audit("INFO", "admin.metrics", {"user_id": user_id})

    # DB info (reuse existing service)
    db_info = service.get_db_info()

    # LLM stats (last 7 days)
    since = _seven_days_ago()
    llm_total = LLMCall.select().where(LLMCall.created_at >= since).count()

    llm_agg = (
        LLMCall.select(
            fn.AVG(LLMCall.latency_ms).alias("avg_latency"),
            fn.SUM(LLMCall.tokens_prompt).alias("total_prompt_tokens"),
            fn.SUM(LLMCall.tokens_completion).alias("total_completion_tokens"),
            fn.SUM(LLMCall.cost_usd).alias("total_cost"),
        )
        .where(LLMCall.created_at >= since)
        .dicts()
        .first()
    ) or {}

    llm_errors = (
        LLMCall.select().where((LLMCall.created_at >= since) & (LLMCall.status == "error")).count()
    )

    llm_stats = {
        "total_calls": llm_total,
        "avg_latency_ms": round(llm_agg.get("avg_latency") or 0, 1),
        "total_prompt_tokens": int(llm_agg.get("total_prompt_tokens") or 0),
        "total_completion_tokens": int(llm_agg.get("total_completion_tokens") or 0),
        "total_cost_usd": round(float(llm_agg.get("total_cost") or 0), 4),
        "error_rate": round(llm_errors / llm_total, 4) if llm_total else 0.0,
    }

    # Scraper stats (last 7 days) -- group by endpoint (provider indicator)
    scraper_rows = (
        CrawlResult.select(
            CrawlResult.endpoint,
            fn.COUNT(CrawlResult.id).alias("total"),
            fn.SUM(
                fn.CASE(None, [(CrawlResult.firecrawl_success == True, 1)], 0)  # noqa: E712
            ).alias("success"),
        )
        .join(RequestModel, on=(CrawlResult.request == RequestModel.id))
        .where(RequestModel.created_at >= since)
        .group_by(CrawlResult.endpoint)
    )
    scraper_stats: dict[str, Any] = {}
    for row in scraper_rows:
        provider = row.endpoint or "unknown"
        total = row.total or 0
        success = row.success or 0
        scraper_stats[provider] = {
            "total": total,
            "success": success,
            "success_rate": round(success / total, 4) if total else 0.0,
        }

    return success_response(
        {
            "database": db_info,
            "llm_7d": llm_stats,
            "scraper_7d": scraper_stats,
        }
    )


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

    query = AuditLog.select()

    if action:
        query = query.where(AuditLog.event == action)

    if since:
        query = query.where(AuditLog.ts >= since)

    # Total before pagination
    total = query.count()

    logs: list[dict[str, Any]] = []
    for entry in query.order_by(AuditLog.ts.desc()).offset(offset).limit(limit):
        details = entry.details_json
        # Optionally filter by user_id inside details
        if user_id_filter is not None:
            if not isinstance(details, dict) or details.get("user_id") != user_id_filter:
                total -= 1
                continue
        logs.append(
            {
                "id": entry.id,
                "timestamp": isotime(entry.ts),
                "level": entry.level,
                "event": entry.event,
                "details": details,
            }
        )

    return success_response(
        {
            "logs": logs,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )
