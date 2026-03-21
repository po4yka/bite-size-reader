"""Edge helpers for scheduling background request processing."""

from __future__ import annotations

import asyncio

from app.core.logging_utils import get_logger, log_exception
from app.di.api import get_current_api_runtime

logger = get_logger(__name__)


async def process_url_request(
    request_id: int, db_path: str | None = None, correlation_id: str | None = None
) -> None:
    processor = get_current_api_runtime().background_processor
    task = asyncio.create_task(
        processor.execute_request(request_id, correlation_id=correlation_id, db_path=db_path)
    )
    tasks = processor._processing_tasks
    tasks.add(task)

    def _on_task_done(t: asyncio.Task) -> None:
        tasks.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            log_exception(
                logger,
                "bg_processing_task_failed",
                exc,
                request_id=request_id,
                correlation_id=correlation_id,
            )

    task.add_done_callback(_on_task_done)
