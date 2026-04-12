"""Aggregation bundle endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.api.exceptions import AuthorizationError, ResourceNotFoundError
from app.api.models.requests import CreateAggregationBundleRequest  # noqa: TC001
from app.api.models.responses import success_response
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
    result = await workflow.aggregate(
        correlation_id=correlation_id,
        user_id=user["user_id"],
        submissions=submissions,
        language="en" if body.lang_preference == "auto" else body.lang_preference,
        metadata={"entrypoint": "api", **dict(body.metadata or {})},
    )
    return success_response(
        {
            "session": {
                "sessionId": result.aggregation.session_id,
                "correlationId": result.aggregation.correlation_id,
                "status": result.aggregation.status,
                "sourceType": result.aggregation.source_type,
                "successfulCount": result.extraction.successful_count,
                "failedCount": result.extraction.failed_count,
                "duplicateCount": result.extraction.duplicate_count,
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
            "session": session,
            "items": items,
            "aggregation": session.get("aggregation_output_json"),
        },
        correlation_id=getattr(request.state, "correlation_id", None),
    )
