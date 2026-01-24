from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

import grpc

from app.api.background_processor import process_url_request
from app.core.logging_utils import log_exception
from app.core.url_utils import compute_dedupe_hash, normalize_url
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)
from app.infrastructure.redis import get_redis
from app.protos import (
    processing_pb2 as _processing_pb2,
    processing_pb2_grpc as _processing_pb2_grpc,
)

# Cast to Any to silence mypy errors with generated code
processing_pb2: Any = _processing_pb2
processing_pb2_grpc: Any = _processing_pb2_grpc

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)

# Set to store background tasks to prevent garbage collection
_background_tasks: set[asyncio.Task] = set()


class ProcessingService(processing_pb2_grpc.ProcessingServiceServicer):
    def __init__(self, cfg: AppConfig, db: DatabaseSessionManager):
        self.cfg = cfg
        self.db = db
        self.request_repo = SqliteRequestRepositoryAdapter(db)
        self.summary_repo = SqliteSummaryRepositoryAdapter(db)

    def _context_active(self, context: grpc.ServicerContext) -> bool:
        """Return True if the gRPC context is still active."""
        cancelled = getattr(context, "cancelled", None)
        if callable(cancelled) and cancelled():
            return False
        is_active = getattr(context, "is_active", None)
        if callable(is_active):
            return bool(is_active())
        return True

    def _max_stream_seconds(self) -> int:
        base = int(getattr(self.cfg.runtime, "request_timeout_sec", 60))
        return max(60, base * 2)

    def _map_status_stage(self, status: str | None, stage: str | None = None) -> tuple[int, int]:
        status_map = {
            "PENDING": processing_pb2.ProcessingStatus.ProcessingStatus_PENDING,
            "PROCESSING": processing_pb2.ProcessingStatus.ProcessingStatus_PROCESSING,
            "COMPLETED": processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
            "FAILED": processing_pb2.ProcessingStatus.ProcessingStatus_FAILED,
        }

        stage_map = {
            "QUEUED": processing_pb2.ProcessingStage.ProcessingStage_QUEUED,
            "EXTRACTION": processing_pb2.ProcessingStage.ProcessingStage_EXTRACTION,
            "SUMMARIZATION": processing_pb2.ProcessingStage.ProcessingStage_SUMMARIZATION,
            "SAVING": processing_pb2.ProcessingStage.ProcessingStage_SAVING,
            "DONE": processing_pb2.ProcessingStage.ProcessingStage_DONE,
        }

        return (
            status_map.get(
                status or "", processing_pb2.ProcessingStatus.ProcessingStatus_UNSPECIFIED
            ),
            stage_map.get(stage or "", processing_pb2.ProcessingStage.ProcessingStage_UNSPECIFIED),
        )

    async def _stream_updates_without_redis(
        self, request_id: int, context: grpc.ServicerContext
    ) -> AsyncGenerator[processing_pb2.ProcessingUpdate]:
        """Poll the database for status updates when Redis is unavailable."""
        start_time = time.monotonic()
        last_status: str | None = None

        while True:
            if not self._context_active(context):
                break

            if time.monotonic() - start_time > self._max_stream_seconds():
                yield processing_pb2.ProcessingUpdate(
                    request_id=request_id,
                    status=processing_pb2.ProcessingStatus.ProcessingStatus_FAILED,
                    stage=processing_pb2.ProcessingStage.ProcessingStage_UNSPECIFIED,
                    message="Processing timed out",
                    progress=0.0,
                    error="timeout",
                )
                break

            req = await self.request_repo.async_get_request_by_id(request_id)
            if not req:
                yield processing_pb2.ProcessingUpdate(
                    request_id=request_id,
                    status=processing_pb2.ProcessingStatus.ProcessingStatus_FAILED,
                    stage=processing_pb2.ProcessingStage.ProcessingStage_UNSPECIFIED,
                    message="Request not found",
                    progress=0.0,
                    error="not_found",
                )
                break

            status_raw = str(req.get("status") or "").lower()
            if status_raw != last_status:
                if status_raw in {"pending", "queued", ""}:
                    status, stage = self._map_status_stage("PENDING", "QUEUED")
                    message = "Request accepted"
                    progress = 0.0
                elif status_raw == "processing":
                    status, stage = self._map_status_stage("PROCESSING", "QUEUED")
                    message = "Processing"
                    progress = 0.5
                elif status_raw == "success":
                    status, stage = self._map_status_stage("COMPLETED", "DONE")
                    message = "Processing completed"
                    progress = 1.0
                elif status_raw in {"error", "failed", "cancelled"}:
                    status, stage = self._map_status_stage("FAILED", None)
                    message = "Processing failed"
                    progress = 1.0
                else:
                    status, stage = self._map_status_stage(None, None)
                    message = f"Unknown status: {status_raw}"
                    progress = 0.0

                update = processing_pb2.ProcessingUpdate(
                    request_id=request_id,
                    status=status,
                    stage=stage,
                    message=message,
                    progress=progress,
                )

                if status == processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED:
                    summary = await self.summary_repo.async_get_summary_by_request(request_id)
                    if summary:
                        update.summary_id = summary["id"]

                yield update
                last_status = status_raw

                if status in (
                    processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
                    processing_pb2.ProcessingStatus.ProcessingStatus_FAILED,
                ):
                    break

            await asyncio.sleep(1.0)

    async def SubmitUrl(  # noqa: N802
        self,
        request: processing_pb2.SubmitUrlRequest,
        context: grpc.ServicerContext,
    ) -> AsyncGenerator[processing_pb2.ProcessingUpdate]:
        url = request.url
        if not url:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "URL is required")
            return

        normalized = normalize_url(url)
        dedupe_hash = compute_dedupe_hash(normalized)

        # Check for existing request if force_refresh is False
        if not request.force_refresh:
            existing = await self.request_repo.async_get_request_by_dedupe_hash(dedupe_hash)
            if existing and existing.get("status") == "success":
                # Check for existing summary
                summary = await self.summary_repo.async_get_summary_by_request(existing["id"])
                if summary:
                    yield processing_pb2.ProcessingUpdate(
                        request_id=existing["id"],
                        status=processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
                        stage=processing_pb2.ProcessingStage.ProcessingStage_DONE,
                        message="Already processed",
                        progress=1.0,
                        summary_id=summary["id"],
                    )
                    return

        # Create or update request
        try:
            if request.force_refresh:
                existing = await self.request_repo.async_get_request_by_dedupe_hash(dedupe_hash)
                if existing:
                    request_id = int(existing["id"])
                    await self.request_repo.async_update_request_status(request_id, "pending")
                else:
                    request_id = await self.request_repo.async_create_request(
                        type_="url",
                        input_url=url,
                        normalized_url=normalized,
                        dedupe_hash=dedupe_hash,
                    )
            else:
                request_id = await self.request_repo.async_create_request(
                    type_="url",
                    input_url=url,
                    normalized_url=normalized,
                    dedupe_hash=dedupe_hash,
                )
        except Exception as e:
            log_exception(logger, "grpc_request_handling_failed", e, request_id=request_id)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to handle request")
            return

        # Start background processing
        task = asyncio.create_task(process_url_request(request_id))
        _background_tasks.add(task)

        def _on_task_done(t: asyncio.Task) -> None:
            _background_tasks.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                log_exception(logger, "grpc_background_task_failed", exc, request_id=request_id)

        task.add_done_callback(_on_task_done)

        # Subscribe to Redis events
        redis = await get_redis(self.cfg)
        if not redis:
            logger.warning("grpc_redis_unavailable", extra={"request_id": request_id})
            yield processing_pb2.ProcessingUpdate(
                request_id=request_id,
                status=processing_pb2.ProcessingStatus.ProcessingStatus_PENDING,
                stage=processing_pb2.ProcessingStage.ProcessingStage_QUEUED,
                message="Request accepted",
                progress=0.0,
            )
            async for update in self._stream_updates_without_redis(request_id, context):
                yield update
            return

        pubsub = redis.pubsub()
        channel = f"processing:request:{request_id}"
        await pubsub.subscribe(channel)

        yield processing_pb2.ProcessingUpdate(
            request_id=request_id,
            status=processing_pb2.ProcessingStatus.ProcessingStatus_PENDING,
            stage=processing_pb2.ProcessingStage.ProcessingStage_QUEUED,
            message="Request accepted",
            progress=0.0,
        )

        start_time = time.monotonic()
        try:
            while True:
                if not self._context_active(context):
                    break

                if time.monotonic() - start_time > self._max_stream_seconds():
                    yield processing_pb2.ProcessingUpdate(
                        request_id=request_id,
                        status=processing_pb2.ProcessingStatus.ProcessingStatus_FAILED,
                        stage=processing_pb2.ProcessingStage.ProcessingStage_UNSPECIFIED,
                        message="Processing timed out",
                        progress=0.0,
                        error="timeout",
                    )
                    break

                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message:
                    continue

                data = json.loads(message["data"])
                status, stage = self._map_status_stage(data.get("status"), data.get("stage"))

                update = processing_pb2.ProcessingUpdate(
                    request_id=data.get("request_id"),
                    status=status,
                    stage=stage,
                    message=data.get("message", ""),
                    progress=data.get("progress", 0.0),
                    error=data.get("error", ""),
                )

                # If completed, try to fetch summary ID if not in payload.
                if update.status == processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED:
                    summary = await self.summary_repo.async_get_summary_by_request(request_id)
                    if summary:
                        update.summary_id = summary["id"]

                yield update

                if update.status in (
                    processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
                    processing_pb2.ProcessingStatus.ProcessingStatus_FAILED,
                ):
                    break
        except Exception as e:
            log_exception(logger, "grpc_streaming_error", e, request_id=request_id)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
