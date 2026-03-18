"""Typing indicator helper for Telegram bot.

Provides a context manager and utility functions for maintaining typing indicators
during long-running operations.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.adapters.external.response_formatter import ResponseFormatter

logger = get_logger(__name__)


class TypingIndicator:
    """Manages periodic typing indicator updates for long operations.

    Telegram typing indicators expire after ~5 seconds, so they need to be
    refreshed periodically during long operations.

    Usage:
        async with TypingIndicator(response_formatter, chat_id):
            # Long operation here
            await process_url()

    Or manually:
        indicator = TypingIndicator(response_formatter, chat_id)
        await indicator.start()
        try:
            await process_url()
        finally:
            await indicator.stop()
    """

    # Telegram typing indicator expires after ~5 seconds, refresh every 4 seconds
    REFRESH_INTERVAL = 4.0

    def __init__(
        self,
        send_chat_action_func: Callable[[int, str], Awaitable[bool]],
        chat_id: int,
        action: str = "typing",
        interval: float | None = None,
    ) -> None:
        self._send_chat_action = send_chat_action_func
        self._chat_id = chat_id
        self._action = action
        self._interval = interval or self.REFRESH_INTERVAL
        self._task: asyncio.Task[Any] | None = None
        self._stop_event = asyncio.Event()

    async def _send_action_once(self, *, initial: bool = False) -> bool:
        """Send one chat-action event and convert failures to diagnostics."""
        try:
            return await self._send_chat_action(self._chat_id, self._action)
        except Exception:
            event = (
                "typing_indicator_initial_send_failed"
                if initial
                else "typing_indicator_periodic_send_failed"
            )
            logger.debug(
                event,
                extra={"chat_id": self._chat_id, "action": self._action},
                exc_info=True,
            )
            return False

    async def _typing_loop(self) -> None:
        """Background task that periodically sends typing indicators."""
        while not self._stop_event.is_set():
            await self._send_action_once(initial=False)
            await asyncio.sleep(self._interval)

    async def start(self) -> None:
        """Start the typing indicator."""
        if self._task is not None:
            return  # Already running

        # Send initial typing indicator
        initial_send_ok = await self._send_action_once(initial=True)
        if not initial_send_ok:
            logger.debug("typing_indicator_start_continues_without_initial_send")

        self._stop_event.clear()
        self._task = asyncio.create_task(self._typing_loop())
        logger.debug(
            "typing_indicator_started",
            extra={"chat_id": self._chat_id, "action": self._action},
        )

    async def stop(self) -> None:
        """Stop the typing indicator."""
        if self._task is None:
            return

        self._stop_event.set()
        self._task.cancel()
        result = await asyncio.gather(self._task, return_exceptions=True)
        task_error = result[0] if result else None
        if isinstance(task_error, Exception) and not isinstance(task_error, asyncio.CancelledError):
            logger.debug("typing_indicator_stop_wait_failed", extra={"error": str(task_error)})

        self._task = None
        logger.debug(
            "typing_indicator_stopped",
            extra={"chat_id": self._chat_id},
        )

    async def __aenter__(self) -> TypingIndicator:
        """Enter async context manager."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        await self.stop()


@asynccontextmanager
async def typing_indicator(
    response_formatter: ResponseFormatter,
    message: Any,
    action: str = "typing",
    interval: float | None = None,
):
    """Context manager for typing indicators.

    Args:
        response_formatter: ResponseFormatter instance with send_chat_action method
        message: Telegram message object (to extract chat_id)
        action: The action type (default: "typing")
        interval: Refresh interval in seconds

    Usage:
        async with typing_indicator(response_formatter, message):
            await long_running_operation()
    """
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None) if chat else None

    if not chat_id or not hasattr(response_formatter, "send_chat_action"):
        # No chat ID or formatter doesn't support typing indicators
        yield
        return

    indicator = TypingIndicator(
        send_chat_action_func=response_formatter.send_chat_action,
        chat_id=chat_id,
        action=action,
        interval=interval,
    )

    await indicator.start()
    try:
        yield indicator
    finally:
        await indicator.stop()


async def send_typing_once(
    response_formatter: ResponseFormatter,
    message: Any,
    action: str = "typing",
) -> bool:
    """Send a single typing indicator (non-refreshing).

    Args:
        response_formatter: ResponseFormatter instance
        message: Telegram message object
        action: The action type (default: "typing")

    Returns:
        True if sent successfully, False otherwise
    """
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None) if chat else None

    if not chat_id or not hasattr(response_formatter, "send_chat_action"):
        return False

    try:
        return await response_formatter.send_chat_action(chat_id, action)
    except Exception:
        return False
