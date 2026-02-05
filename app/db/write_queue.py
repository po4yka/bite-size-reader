"""Background queue for cancellation-safe DB persistence.

DB write operations enqueued here are processed sequentially by a dedicated
asyncio worker task.  Because the worker is bot-scoped (not request-scoped),
it is never cancelled by URL-processing timeouts -- writes always complete.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# Sentinel used to signal the worker to shut down.
_SENTINEL = None


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
        self._queue: asyncio.Queue[tuple[Callable[[], Awaitable[None]], str, str] | None] = (
            asyncio.Queue(maxsize=maxsize)
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
            await asyncio.wait_for(self._worker_task, timeout=timeout)
        except TimeoutError:
            logger.warning("DbWriteQueue worker did not finish within %.1fs; cancelling", timeout)
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
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
        await self._queue.put((operation, operation_name, correlation_id))
        logger.debug(
            "Enqueued %s (correlation_id=%s, pending=%d)",
            operation_name,
            correlation_id,
            self._queue.qsize(),
        )

    # ------------------------------------------------------------------
    # Internal worker
    # ------------------------------------------------------------------

    async def _worker(self) -> None:
        """Process queued items sequentially until the sentinel is received."""
        logger.debug("DbWriteQueue worker loop started")
        while True:
            item = await self._queue.get()
            if item is _SENTINEL:
                # Drain any remaining real items before exiting.
                await self._drain()
                self._queue.task_done()
                break
            await self._process_item(item)
            self._queue.task_done()
        logger.debug("DbWriteQueue worker loop exited")

    async def _drain(self) -> None:
        """Process all items remaining in the queue after the sentinel."""
        drained = 0
        while not self._queue.empty():
            item = self._queue.get_nowait()
            if item is _SENTINEL:
                self._queue.task_done()
                continue
            await self._process_item(item)
            self._queue.task_done()
            drained += 1
        if drained:
            logger.info("Drained %d remaining items during shutdown", drained)

    async def _process_item(
        self,
        item: tuple[Callable[[], Awaitable[None]], str, str],
    ) -> None:
        """Execute a single write operation, catching errors."""
        operation, operation_name, correlation_id = item
        try:
            await self._execute(operation)
        except Exception:
            logger.exception(
                "DbWriteQueue: %s failed (correlation_id=%s)",
                operation_name,
                correlation_id,
            )

    async def _execute(self, operation: Callable[[], Awaitable[None]]) -> None:
        """Run the write callable.

        Extracted as a separate method so tests can override or mock it.
        """
        await operation()
