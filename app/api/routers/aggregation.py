"""Aggregation bundle endpoints."""

from __future__ import annotations

import contextlib
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies.database import get_session_manager
from app.api.exceptions import AuthorizationError, ResourceNotFoundError, ValidationError
from app.api.models.requests import CreateAggregationBundleRequest  # noqa: TC001
from app.api.models.responses import success_response
from app.api.models.responses.common import PaginationInfo
from app.api.routers.auth import get_current_user
from app.application.dto.aggregation import SourceSubmission
from app.application.services.aggregation_rollout import AggregationRolloutGate
from app.application.services.multi_source_aggregation_service import (
    MultiSourceAggregationService,
)
from app.config import load_config
from app.core.logging_utils import generate_correlation_id
from app.di.api import resolve_api_runtime
from app.di.repositories import build_aggregation_session_repository, build_user_repository
from app.di.shared import build_async_audit_sink
from app.domain.models.source import AggregationSessionStatus  # noqa: TC001
from app.security.ssrf import is_url_safe

router = APIRouter()


def _get_aggregation_workflow(request: Request) -> MultiSourceAggregationService:
    runtime = resolve_api_runtime(request)
    return MultiSourceAggregationService(
        content_extractor=runtime.background_processor.url_processor.content_extractor,
        aggregation_session_repo=build_aggregation_session_repository(runtime.db),
        llm_client=runtime.core.llm_client,
    )


def _get_rollout_gate(request: Request) -> AggregationRolloutGate:
    runtime = resolve_api_runtime(request)
    cfg = getattr(runtime, "cfg", None) or load_config(allow_stub_telegram=True)
    db = getattr(runtime, "db", None)
    return AggregationRolloutGate(
        cfg=cfg,
        user_repo=build_user_repository(db) if db is not None else None,
    )


def _resolve_db(request: Request) -> Any:
    with contextlib.suppress(RuntimeError):
        return resolve_api_runtime(request).db
    return get_session_manager(request)


def _ensure_public_bundle_urls(
    *,
    body: CreateAggregationBundleRequest,
    audit: Any,
    audit_context: dict[str, Any],
) -> None:
    for position, item in enumerate(body.items):
        url = str(item.url)
        safe, reason = is_url_safe(url)
        if safe:
            continue
        details = {
            **audit_context,
            "position": position,
            "url": url,
            "reason": reason,
        }
        audit("WARNING", "aggregation.bundle_create_blocked_ssrf", details)
        raise ValidationError(
            "Aggregation bundle contains a blocked URL",
            details={
                "position": position,
                "url": url,
                "reason": reason,
            },
        )


async def _ensure_aggregation_available(
    *,
    gate: AggregationRolloutGate,
    user_id: int,
) -> None:
    decision = await gate.evaluate(user_id)
    if decision.enabled:
        return
    if decision.stage.value == "disabled":
        raise ResourceNotFoundError("Aggregation feature", "v1/aggregations")
    raise AuthorizationError(decision.reason)


def _build_progress_payload(session: dict[str, Any]) -> dict[str, Any]:
    total_items = int(session.get("total_items") or 0)
    successful_count = int(session.get("successful_count") or 0)
    failed_count = int(session.get("failed_count") or 0)
    duplicate_count = int(session.get("duplicate_count") or 0)
    processed_items = min(total_items, successful_count + failed_count + duplicate_count)
    completion_percent = int(session.get("progress_percent") or 0)
    if total_items > 0 and completion_percent == 0 and processed_items > 0:
        completion_percent = int((processed_items / total_items) * 100)
    return {
        "totalItems": total_items,
        "processedItems": processed_items,
        "successfulCount": successful_count,
        "failedCount": failed_count,
        "duplicateCount": duplicate_count,
        "completionPercent": completion_percent,
    }


def _build_failure_payload(record: dict[str, Any]) -> dict[str, Any] | None:
    code = str(record.get("failure_code") or "").strip()
    message = str(record.get("failure_message") or "").strip()
    details = record.get("failure_details_json")
    if not code and not message and not details:
        return None
    return {
        "code": code or None,
        "message": message or None,
        "details": details,
    }


def _serialize_persisted_session(session: dict[str, Any]) -> dict[str, Any]:
    return {
        **session,
        "progress": _build_progress_payload(session),
        "failure": _build_failure_payload(session),
    }


@router.post("")
async def create_aggregation_bundle(
    body: CreateAggregationBundleRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    workflow: MultiSourceAggregationService = Depends(_get_aggregation_workflow),
    rollout_gate: AggregationRolloutGate = Depends(_get_rollout_gate),
) -> dict[str, Any]:
    """Run mixed-source aggregation for one submitted bundle."""

    await _ensure_aggregation_available(gate=rollout_gate, user_id=user["user_id"])
    correlation_id = getattr(request.state, "correlation_id", None) or generate_correlation_id()
    runtime = resolve_api_runtime(request)
    audit = build_async_audit_sink(_resolve_db(request))
    audit_context = {
        "user_id": user["user_id"],
        "client_id": user.get("client_id"),
        "correlation_id": correlation_id,
        "item_count": len(body.items),
        "lang_preference": body.lang_preference,
    }
    audit("INFO", "aggregation.bundle_create_requested", audit_context)
    _ensure_public_bundle_urls(body=body, audit=audit, audit_context=audit_context)
    submissions = [
        SourceSubmission.from_url(
            str(item.url),
            metadata={
                **dict(item.metadata or {}),
                **({"source_kind_hint": item.source_kind_hint} if item.source_kind_hint else {}),
            },
        )
        for item in body.items
    ]
    repo = build_aggregation_session_repository(runtime.db)
    try:
        result = await workflow.aggregate(
            correlation_id=correlation_id,
            user_id=user["user_id"],
            submissions=submissions,
            language=body.lang_preference,
            metadata={
                **dict(body.metadata or {}),
                "entrypoint": "api",
                "client_id": user.get("client_id"),
            },
        )
    except Exception as exc:
        audit(
            "ERROR",
            "aggregation.bundle_create_failed",
            {
                **audit_context,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise
    persisted_session = await repo.async_get_aggregation_session(result.aggregation.session_id)
    audit(
        "INFO",
        "aggregation.bundle_create_succeeded",
        {
            **audit_context,
            "session_id": result.aggregation.session_id,
            "status": result.aggregation.status,
            "successful_count": result.extraction.successful_count,
            "failed_count": result.extraction.failed_count,
            "duplicate_count": result.extraction.duplicate_count,
        },
    )
    progress_source = persisted_session or {
        "total_items": result.aggregation.total_items,
        "successful_count": result.extraction.successful_count,
        "failed_count": result.extraction.failed_count,
        "duplicate_count": result.extraction.duplicate_count,
        "progress_percent": 100 if result.aggregation.status != "failed" else 0,
    }
    return success_response(
        {
            "session": {
                "sessionId": result.aggregation.session_id,
                "correlationId": result.aggregation.correlation_id,
                "status": (persisted_session or {}).get("status", result.aggregation.status),
                "sourceType": result.aggregation.source_type,
                "successfulCount": result.extraction.successful_count,
                "failedCount": result.extraction.failed_count,
                "duplicateCount": result.extraction.duplicate_count,
                "processingTimeMs": (persisted_session or {}).get("processing_time_ms"),
                "queuedAt": (persisted_session or {}).get("queued_at"),
                "startedAt": (persisted_session or {}).get("started_at"),
                "completedAt": (persisted_session or {}).get("completed_at"),
                "lastProgressAt": (persisted_session or {}).get("last_progress_at"),
                "progress": _build_progress_payload(progress_source),
                "failure": _build_failure_payload(persisted_session or {}),
            },
            "aggregation": result.aggregation.model_dump(mode="json"),
            "items": [
                {
                    "position": item.position,
                    "itemId": item.item_id,
                    "sourceItemId": item.source_item_id,
                    "sourceKind": item.source_kind.value,
                    "status": item.status,
                    "requestId": item.request_id,
                    "failure": item.failure.model_dump(mode="json") if item.failure else None,
                }
                for item in result.extraction.items
            ],
        },
        correlation_id=correlation_id,
    )


@router.get("")
async def list_aggregation_bundles(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: AggregationSessionStatus | None = Query(default=None),
    user: dict[str, Any] = Depends(get_current_user),
    rollout_gate: AggregationRolloutGate = Depends(_get_rollout_gate),
) -> dict[str, Any]:
    """Return recent aggregation sessions for the authenticated user."""

    await _ensure_aggregation_available(gate=rollout_gate, user_id=user["user_id"])
    runtime = resolve_api_runtime(request)
    repo = build_aggregation_session_repository(runtime.db)
    status_value = status.value if status is not None else None
    sessions = await repo.async_get_user_aggregation_sessions(
        user["user_id"],
        limit=limit + 1,
        offset=offset,
        status=status_value,
    )
    total = await repo.async_count_user_aggregation_sessions(user["user_id"], status=status_value)
    has_more = len(sessions) > limit
    visible_sessions = sessions[:limit]
    return success_response(
        {
            "sessions": [_serialize_persisted_session(session) for session in visible_sessions],
        },
        correlation_id=getattr(request.state, "correlation_id", None),
        pagination=PaginationInfo(
            total=total,
            limit=limit,
            offset=offset,
            has_more=has_more,
        ),
    )


@router.get("/{session_id}")
async def get_aggregation_bundle(
    session_id: int,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    rollout_gate: AggregationRolloutGate = Depends(_get_rollout_gate),
) -> dict[str, Any]:
    """Return one persisted aggregation session with bundle items and output."""

    await _ensure_aggregation_available(gate=rollout_gate, user_id=user["user_id"])
    runtime = resolve_api_runtime(request)
    repo = build_aggregation_session_repository(runtime.db)
    session = await repo.async_get_aggregation_session(session_id)
    if session is None:
        raise ResourceNotFoundError("Aggregation session", session_id)
    if session.get("user") != user["user_id"]:
        raise AuthorizationError("Access denied")

    items = await repo.async_get_aggregation_session_items(session_id)
    return success_response(
        {
            "session": _serialize_persisted_session(session),
            "items": items,
            "aggregation": session.get("aggregation_output_json"),
        },
        correlation_id=getattr(request.state, "correlation_id", None),
    )
