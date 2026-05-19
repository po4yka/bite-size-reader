"""Server-Sent Events endpoint for streaming summary progress."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import orjson
from fastapi import APIRouter, Depends, HTTPException, Request as FastAPIRequest, status
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.adapters.content.streaming import get_stream_hub
from app.api.routers.auth import get_current_user
from app.application.services.request_service import RequestService
from app.domain.exceptions.domain_exceptions import (
    ResourceNotFoundError as DomainResourceNotFoundError,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

router = APIRouter()

HEARTBEAT_INTERVAL = 15  # seconds


def _get_request_service(request: FastAPIRequest) -> RequestService:
    """Resolve the shared request workflow service from API runtime."""
    import contextlib

    with contextlib.suppress(RuntimeError):
        from app.di.api import resolve_api_runtime

        return cast("RequestService", resolve_api_runtime(request).request_service)

    from app.api.dependencies.database import (
        get_crawl_result_repository,
        get_llm_repository,
        get_request_repository,
        get_session_manager,
        get_summary_repository,
    )

    db = get_session_manager(request)
    return RequestService(
        db=db,
        request_repository=get_request_repository(db, request),
        summary_repository=get_summary_repository(db, request),
        crawl_result_repository=get_crawl_result_repository(db, request),
        llm_repository=get_llm_repository(db, request),
    )


@router.get("/{request_id}/stream")
async def stream_request(
    request_id: int,
    fastapi_request: FastAPIRequest,
    user: dict[str, Any] = Depends(get_current_user),
    request_service: RequestService = Depends(_get_request_service),
) -> EventSourceResponse:
    """Stream processing events for a specific request via SSE.

    Replays buffered events first (ring-buffer backlog), then delivers live
    events until a terminal ``done`` or ``error`` event is received.  The
    connection is kept alive with automatic SSE comment-line heartbeats every
    ``HEARTBEAT_INTERVAL`` seconds.

    Returns 403 when the request does not belong to the authenticated user.
    """
    # Load the Request row and verify ownership — mirror get_request pattern.
    try:
        details = await request_service.get_request_by_id(user["user_id"], request_id)
    except Exception as exc:
        if isinstance(exc, DomainResourceNotFoundError):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Request not found or access denied",
            ) from exc
        logger.bind(request_id=str(request_id)).error(
            "stream.error",
            error=repr(exc),
        )
        try:
            import sentry_sdk

            sentry_sdk.add_breadcrumb(
                category="stream",
                level="error",
                data={"request_id": request_id, "error": repr(exc)},
            )
        except ImportError:
            pass
        raise

    del details  # ownership confirmed; we don't need the full details object

    hub = get_stream_hub()

    async def event_generator() -> AsyncIterator[dict[str, Any]]:
        subscription = hub.subscribe(str(request_id))
        try:
            async for event in subscription:
                yield {
                    "event": event.kind,
                    "data": orjson.dumps(
                        {
                            "kind": event.kind,
                            "payload": event.payload,
                            "timestamp": event.timestamp.isoformat(),
                            "correlation_id": event.correlation_id,
                        }
                    ).decode(),
                }
                if event.kind in ("done", "error"):
                    return
        except (asyncio.CancelledError, GeneratorExit):
            # Client disconnect: stop iterating; the underlying summarization continues.
            return

    return EventSourceResponse(
        event_generator(),
        ping=HEARTBEAT_INTERVAL,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
