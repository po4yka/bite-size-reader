"""Thread-safe progress tracking utility for Telegram message updates.

This module provides a reusable ProgressTracker class for tracking progress
of batch operations and sending updates to Telegram in a thread-safe manner.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class ProgressFormatter(Protocol):
    """Protocol for formatting progress messages."""

    async def format_and_send(self, current: int, total: int, message_id: int | None) -> int | None:
        """Format and send/edit a progress message.

        Args:
            current: Current progress count
            total: Total items to process
            message_id: Optional message ID to edit

        Returns:
            Message ID for future edits, or None if unavailable
        """
        ...


class ProgressTracker:
    """Thread-safe progress tracking with non-blocking queue-based updates.

    This class provides atomic progress tracking with configurable update intervals
    and thresholds. It uses a queue-based approach to decouple progress increments
    from actual message sends, preventing blocking of worker tasks.

    Features:
    - Atomic counter updates with asyncio.Lock
    - Non-blocking progress updates via queue (maxsize=1)
    - Configurable time and progress thresholds
    - Graceful shutdown with event signaling
    - Automatic queue overflow handling
    - Separate queue processor for concurrent updates

    Example:
        ```python
        async def send_progress(current, total, msg_id):
            # Custom logic to send/edit message
            return new_msg_id

        tracker = ProgressTracker(
            total=100,
            progress_formatter=send_progress,
            initial_message_id=None
        )

        # Start the queue processor
        processor_task = asyncio.create_task(tracker.process_update_queue())

        # In worker tasks
        await tracker.increment_and_update()

        # After all work is done
        tracker.mark_complete()
        await processor_task
        ```
    """

    def __init__(
        self,
        total: int,
        progress_formatter: Callable[[int, int, int | None], Any],
        initial_message_id: int | None = None,
        *,
        update_interval: float = 1.0,
        small_batch_threshold: int = 10,
        progress_threshold_percentage: float = 5.0,
    ):
        """Initialize the progress tracker.

        Args:
            total: Total number of items to process
            progress_formatter: Async function to format and send progress updates
            initial_message_id: Optional initial message ID for edits
            update_interval: Minimum time in seconds between updates (default: 1.0)
            small_batch_threshold: Batch size threshold for more frequent updates (default: 10)
            progress_threshold_percentage: Percentage of progress before update (default: 5%)
        """
        self.total = total
        self._completed = 0
        self._lock = asyncio.Lock()
        self._last_update_time = 0.0
        self._last_displayed = 0
        self.update_interval = update_interval
        self.small_batch_threshold = small_batch_threshold
        self.progress_threshold_percentage = progress_threshold_percentage
        self.progress_formatter = progress_formatter
        self.message_id = initial_message_id
        self._update_queue: asyncio.Queue[tuple[int, int]] = asyncio.Queue(maxsize=1)
        self._queue_overflow_logged = False
        self._shutdown_event = asyncio.Event()

    async def increment_and_update(self) -> tuple[int, int]:
        """Atomically increment counter and queue progress update if needed.

        This method is designed to be called from worker tasks. It increments
        the progress counter atomically and, if update thresholds are met,
        queues a progress update for the background processor.

        Returns:
            Tuple of (completed, total) counts
        """
        # Fast path: only increment counter under lock
        async with self._lock:
            self._completed += 1
            current_time = time.time()

            # Calculate thresholds
            progress_threshold = max(1, int(self.total * self.progress_threshold_percentage / 100))
            # For small batches, be more responsive
            if self.total <= self.small_batch_threshold:
                progress_threshold = 1

            # Check both time and progress thresholds
            time_threshold_met = current_time - self._last_update_time >= self.update_interval
            progress_threshold_met = self._completed - self._last_displayed >= progress_threshold

            # Only enqueue updates if we actually made forward progress
            made_progress = self._completed > self._last_displayed
            should_update = False
            if made_progress:
                # Always surface meaningful progress jumps immediately or send periodic heartbeats
                if progress_threshold_met or time_threshold_met:
                    should_update = True

            if should_update:
                self._last_update_time = current_time
                self._last_displayed = self._completed

            completed = self._completed

        # Slow path: enqueue update outside lock to prevent deadlocks
        if should_update:
            try:
                self._update_queue.put_nowait((completed, self.total))
                self._queue_overflow_logged = False
            except asyncio.QueueFull:
                # Drop oldest update and add new one
                try:
                    dropped_update = self._update_queue.get_nowait()
                    self._update_queue.task_done()
                except asyncio.QueueEmpty:
                    dropped_update = None

                if not self._queue_overflow_logged:
                    logger.debug(
                        "progress_update_queue_full",
                        extra={
                            "last_displayed": self._last_displayed,
                            "completed": completed,
                            "dropped": dropped_update,
                        },
                    )
                    self._queue_overflow_logged = True

                self._update_queue.put_nowait((completed, self.total))

        # Signal shutdown if complete
        if completed >= self.total:
            self._shutdown_event.set()

        return completed, self.total

    async def process_update_queue(self) -> None:
        """Process queued progress updates in the background.

        This method should be run as a separate task. It continuously processes
        updates from the queue until shutdown is signaled and the queue is empty.

        The processor calls the progress_formatter with the current progress
        and updates the message_id if a new one is returned.
        """
        while True:
            # Exit when shutdown is signaled and queue is empty
            if self._shutdown_event.is_set() and self._update_queue.empty():
                break

            try:
                # Wait for updates with timeout to allow checking shutdown
                completed, total = await asyncio.wait_for(self._update_queue.get(), timeout=0.5)
            except TimeoutError:
                continue

            try:
                # Call the formatter to send/edit the message
                new_message_id = await self.progress_formatter(completed, total, self.message_id)
                if new_message_id is not None:
                    self.message_id = new_message_id
            except Exception as e:
                logger.warning(
                    "progress_update_failed",
                    extra={
                        "error": str(e),
                        "completed": completed,
                        "total": total,
                    },
                )
            finally:
                self._update_queue.task_done()

    def mark_complete(self) -> None:
        """Signal that no further updates will be enqueued.

        This should be called after all worker tasks are done to allow
        the queue processor to exit gracefully.
        """
        self._shutdown_event.set()

    @property
    def completed(self) -> int:
        """Get the current completed count (not thread-safe, for display only)."""
        return self._completed

    @property
    def is_complete(self) -> bool:
        """Check if processing is complete (not thread-safe, for display only)."""
        return self._completed >= self.total
