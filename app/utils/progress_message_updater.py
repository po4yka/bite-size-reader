"""
Progress Message Updater.

Manages periodic updates to a progress message with elapsed time tracking.
Similar to TypingIndicator but for editable progress messages in Reader mode.
"""

import asyncio
import time
from collections.abc import Callable
from typing import Any

from app.core.progress_tracker import ProgressTracker


class ProgressMessageUpdater:
    """Manages periodic updates to a progress message with elapsed time.

    Usage:
        async with ProgressMessageUpdater(tracker, message) as updater:
            formatter = lambda elapsed: f"Processing... ({elapsed:.0f}s)"
            await updater.start(formatter)
            # ... do work ...
            await updater.finalize("Done!")
    """

    def __init__(
        self,
        progress_tracker: ProgressTracker,
        message: Any,
        update_interval: float = 4.0,
    ):
        """Initialize progress message updater.

        Args:
            progress_tracker: ProgressTracker instance for message updates
            message: Telegram message object
            update_interval: Seconds between progress updates (default: 4.0)
        """
        self._tracker = progress_tracker
        self._message = message
        self._interval = update_interval
        self._start_time = time.time()
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._current_formatter: Callable[[float], str] | None = None

    async def start(self, formatter: Callable[[float], str]) -> None:
        """Start periodic progress updates.

        Args:
            formatter: Function that takes elapsed_sec and returns message text
        """
        self._current_formatter = formatter
        self._stop_event.clear()
        self._task = asyncio.create_task(self._update_loop())

    async def update_formatter(self, formatter: Callable[[float], str]) -> None:
        """Change the formatter function (for phase transitions).

        Args:
            formatter: New formatter function
        """
        self._current_formatter = formatter
        # Trigger immediate update with new formatter
        if self._current_formatter:
            elapsed = time.time() - self._start_time
            text = self._current_formatter(elapsed)
            await self._tracker.update(self._message, text)

    async def finalize(self, final_text: str) -> None:
        """Stop updates and set final message.

        Args:
            final_text: Final message text to display
        """
        # Stop the update loop
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        # Send final message
        await self._tracker.finalize(self._message, final_text)

    async def _update_loop(self) -> None:
        """Internal loop for periodic progress updates."""
        try:
            while not self._stop_event.is_set():
                if self._current_formatter:
                    elapsed = time.time() - self._start_time
                    text = self._current_formatter(elapsed)
                    await self._tracker.update(self._message, text)

                # Wait for next update interval or stop signal
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
                    break  # Stop event was set
                except TimeoutError:
                    continue  # Interval elapsed, continue loop

        except asyncio.CancelledError:
            pass  # Task was cancelled, exit gracefully

    async def __aenter__(self) -> "ProgressMessageUpdater":
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        # Stop updates on exit (but don't finalize - caller should do that)
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
