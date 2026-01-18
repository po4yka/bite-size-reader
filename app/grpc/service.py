from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

import grpc

from app.api.background_processor import process_url_request
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
            logger.error(f"Failed to handle request: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to handle request")
            return

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
            logger.error(f"Streaming error: {e}")
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
