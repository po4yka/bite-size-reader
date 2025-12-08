from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

import grpc

from app.api.background_processor import process_url_request
from app.core.url_utils import compute_dedupe_hash, normalize_url
from app.db.models import Request
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
    from app.db.database import Database

logger = logging.getLogger(__name__)

# Set to store background tasks to prevent garbage collection
_background_tasks: set[asyncio.Task] = set()


class ProcessingService(processing_pb2_grpc.ProcessingServiceServicer):
    def __init__(self, cfg: AppConfig, db: Database):
        self.cfg = cfg
        self.db = db

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
            existing = Request.get_or_none(Request.dedupe_hash == dedupe_hash)
            if existing and existing.status == "success":
                # Check for existing summary
                from app.db.models import Summary

                summary = Summary.get_or_none(Summary.request == existing)
                if summary:
                    yield processing_pb2.ProcessingUpdate(
                        request_id=existing.id,
                        status=processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
                        stage=processing_pb2.ProcessingStage.ProcessingStage_DONE,
                        message="Already processed",
                        progress=1.0,
                        summary_id=summary.id,
                    )
                    return

        # Create new request
        try:
            req_model = Request.create(
                type="url",
                input_url=url,
                normalized_url=normalized,
                dedupe_hash=dedupe_hash
                if not request.force_refresh
                else None,  # Allow duplicates if forced? Or update existing?
                # Ideally if forced, we might want to create a new one or reset the old one.
                # For simplicity, if force_refresh, we ignore dedupe logic or we just create a new one (duplicate hash constraint might fail though).
                # If unique constraint on dedupe_hash exists, we must handle it.
                # Request model has `dedupe_hash = peewee.TextField(null=True, unique=True)`
                # So if force_refresh is true, we should probably NULL the dedupe hash of the new request
                # OR we accept that we can't have two active requests for same URL?
                # Logic in `routers/requests.py` usually checks first.
                # Let's assume for now we just create a new request and maybe suffix dedupe hash or just leave it null if forced.
            )
            # If force_refresh is True, we might want to bypass dedupe check.
            # But the UNIQUE constraint is in DB.
            # If we want to re-process, maybe we should reuse the existing request ID or delete the old one?
            # Safe bet: if exists, reuse it and reset status.

            if request.force_refresh:
                existing = Request.get_or_none(Request.dedupe_hash == dedupe_hash)
                if existing:
                    existing.status = "pending"
                    existing.save()
                    req_model = existing

        except Exception as e:
            logger.error(f"Failed to create request: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to create request")
            return

        request_id = req_model.id

        # Start background processing
        task = asyncio.create_task(process_url_request(request_id))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        # Subscribe to Redis events
        redis = await get_redis(self.cfg)
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

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                data = json.loads(message["data"])

                # Map string status to enum
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

                update = processing_pb2.ProcessingUpdate(
                    request_id=data.get("request_id"),
                    status=status_map.get(
                        data.get("status"),
                        processing_pb2.ProcessingStatus.ProcessingStatus_UNSPECIFIED,
                    ),
                    stage=stage_map.get(
                        data.get("stage"),
                        processing_pb2.ProcessingStage.ProcessingStage_UNSPECIFIED,
                    ),
                    message=data.get("message", ""),
                    progress=data.get("progress", 0.0),
                    error=data.get("error", ""),
                )

                # If completed, try to fetch summary ID if not in payload (payload doesn't have it yet, maybe I should add it to BG processor payload?)
                # I didn't add summary_id to payload in BG processor. I can fetch it from DB if status is COMPLETED.
                if update.status == processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED:
                    from app.db.models import Summary

                    summary = Summary.get_or_none(Summary.request_id == request_id)
                    if summary:
                        update.summary_id = summary.id

                yield update

                if update.status in (
                    processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
                    processing_pb2.ProcessingStatus.ProcessingStatus_FAILED,
                ):
                    break
        except Exception as e:
            logger.error(f"Streaming error: {e}")
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
