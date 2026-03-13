"""Background queue for cancellation-safe DB persistence.

DB write operations enqueued here are processed sequentially by a dedicated
asyncio worker task.  Because the worker is bot-scoped (not request-scoped),
it is never cancelled by URL-processing timeouts -- writes always complete.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# Sentinel used to signal the worker to shut down.
_SENTINEL = None


@dataclass(slots=True)
class _WriteTask:
    operation: Callable[[], Awaitable[None]]
    operation_name: str
    correlation_id: str


@dataclass(slots=True)
class _BatchWriteTask:
    batch_key: str
    execute_batch: Callable[[list[Any]], Awaitable[None]]
    payload: Any
    operation_name: str
    correlation_id: str


class DbWriteQueue:
    """Sequentially processes DB writes in a background asyncio task.

    Usage::

        queue = DbWriteQueue(maxsize=256)
        queue.start()

        # From any request handler -- returns immediately:
        await queue.enqueue(
            lambda: save_summary(request_id, payload),
            operation_name="save_summary",
            correlation_id="abc-123",
        )

        # On bot shutdown:
        await queue.stop(timeout=30.0)
    """

    def __init__(self, maxsize: int = 256) -> None:
        """Initialize the write queue.

        Args:
            maxsize: Maximum number of pending operations before backpressure
                     is applied via ``enqueue`` blocking.
        """
        self._queue: asyncio.Queue[_WriteTask | _BatchWriteTask | None] = asyncio.Queue(
            maxsize=maxsize
        )
        self._worker_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Spawn the background worker coroutine.

        Must be called once after the event loop is running.
        """
        if self._worker_task is not None:
            logger.warning("DbWriteQueue.start() called but worker is already running")
            return
        self._worker_task = asyncio.create_task(self._worker(), name="db-write-queue-worker")
        logger.info("DbWriteQueue worker started (maxsize=%d)", self._queue.maxsize)

    async def stop(self, timeout: float = 30.0) -> None:
        """Signal shutdown and wait for the worker to drain remaining items.

        Args:
            timeout: Maximum seconds to wait for the worker to finish
                     processing remaining items before giving up.
        """
        if self._worker_task is None:
            return

        # Push sentinel so the worker exits its loop.
        await self._queue.put(_SENTINEL)

        try:
            async with asyncio.timeout(timeout):
                await self._worker_task
        except TimeoutError:
            logger.warning("DbWriteQueue worker did not finish within %.1fs; cancelling", timeout)
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                logger.debug("DbWriteQueue worker cancellation acknowledged")
                return
        finally:
            self._worker_task = None
            logger.info("DbWriteQueue stopped")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enqueue(
        self,
        operation: Callable[[], Awaitable[None]],
        *,
        operation_name: str = "db_write",
        correlation_id: str = "",
    ) -> None:
        """Enqueue a DB write operation for background execution.

        This method awaits only until the item is placed on the internal
        queue.  The actual DB work happens later in the worker task.

        Args:
            operation: An async callable (zero-arg) that performs the write.
            operation_name: Human-readable label for logging.
            correlation_id: Correlation ID for tracing.

        Raises:
            asyncio.QueueFull: If the queue is at capacity and the caller
                               uses ``enqueue_nowait`` (not this method --
                               this method blocks until space is available).
        """
        await self._queue.put(_WriteTask(operation, operation_name, correlation_id))
        logger.debug(
            "Enqueued %s (correlation_id=%s, pending=%d)",
            operation_name,
            correlation_id,
            self._queue.qsize(),
        )

    async def enqueue_batch(
        self,
        payload: Any,
        *,
        batch_key: str,
        execute_batch: Callable[[list[Any]], Awaitable[None]],
        operation_name: str = "db_write_batch",
        correlation_id: str = "",
    ) -> None:
        """Enqueue a batchable write payload for grouped execution."""
        await self._queue.put(
            _BatchWriteTask(
                batch_key=batch_key,
                execute_batch=execute_batch,
                payload=payload,
                operation_name=operation_name,
                correlation_id=correlation_id,
            )
        )
        logger.debug(
            "Enqueued batch payload %s (batch_key=%s, pending=%d)",
            operation_name,
            batch_key,
            self._queue.qsize(),
        )

    # ------------------------------------------------------------------
    # Internal worker
    # ------------------------------------------------------------------

    async def _worker(self) -> None:
        """Process queued items sequentially until the sentinel is received."""
        logger.debug("DbWriteQueue worker loop started")
        while True:
            items, stop_requested = await self._next_items()
            if items:
                await self._process_items(items)
                for _ in items:
                    self._queue.task_done()
            if stop_requested:
                await self._drain()
                break
        logger.debug("DbWriteQueue worker loop exited")

    async def _next_items(self) -> tuple[list[_WriteTask | _BatchWriteTask], bool]:
        """Pull the next available queue snapshot for ordered processing."""
        item = await self._queue.get()
        if item is _SENTINEL:
            self._queue.task_done()
            return [], True

        items: list[_WriteTask | _BatchWriteTask] = [item]
        stop_requested = False

        while True:
            try:
                queued = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            if queued is _SENTINEL:
                self._queue.task_done()
                stop_requested = True
                break

            items.append(queued)

        return items, stop_requested

    async def _drain(self) -> None:
        """Process all items remaining in the queue after the sentinel."""
        drained_items: list[_WriteTask | _BatchWriteTask] = []
        while not self._queue.empty():
            item = self._queue.get_nowait()
            if item is _SENTINEL:
                self._queue.task_done()
                continue
            drained_items.append(item)

        if drained_items:
            await self._process_items(drained_items)
            for _ in drained_items:
                self._queue.task_done()
            logger.info("Drained %d remaining items during shutdown", len(drained_items))

    async def _process_items(self, items: list[_WriteTask | _BatchWriteTask]) -> None:
        """Execute a queue snapshot, batching compatible items when possible."""
        index = 0
        while index < len(items):
            item = items[index]
            if isinstance(item, _BatchWriteTask):
                await self._process_batch_write(items, index)
                batch_size = self._batch_span(items, index)
                index += batch_size
                continue

            await self._process_item(item)
            index += 1

    def _batch_span(self, items: list[_WriteTask | _BatchWriteTask], start: int) -> int:
        """Return the number of consecutive items compatible with a batch task."""
        first = items[start]
        if not isinstance(first, _BatchWriteTask):
            return 1

        size = 1
        for queued in items[start + 1 :]:
            if not isinstance(queued, _BatchWriteTask) or queued.batch_key != first.batch_key:
                break
            size += 1
        return size

    async def _process_batch_write(
        self,
        items: list[_WriteTask | _BatchWriteTask],
        start: int,
    ) -> None:
        """Execute a consecutive run of batchable items with one callback."""
        batch_item = items[start]
        if not isinstance(batch_item, _BatchWriteTask):
            return

        batch_size = self._batch_span(items, start)
        payloads = [
            queued.payload
            for queued in items[start : start + batch_size]
            if isinstance(queued, _BatchWriteTask)
        ]
        try:
            await batch_item.execute_batch(payloads)
        except Exception:
            logger.exception(
                "DbWriteQueue: %s batch failed (batch_key=%s, count=%d)",
                batch_item.operation_name,
                batch_item.batch_key,
                len(payloads),
            )

    async def _process_item(self, item: _WriteTask | _BatchWriteTask) -> None:
        """Execute a single non-batched write operation, catching errors."""
        if isinstance(item, _BatchWriteTask):
            await self._process_batch_write([item], 0)
            return

        try:
            await self._execute(item.operation)
        except Exception:
            logger.exception(
                "DbWriteQueue: %s failed (correlation_id=%s)",
                item.operation_name,
                item.correlation_id,
            )

    async def _execute(self, operation: Callable[[], Awaitable[None]]) -> None:
        """Run the write callable.

        Extracted as a separate method so tests can override or mock it.
        """
        await operation()
