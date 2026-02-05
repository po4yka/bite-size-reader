"""Graceful shutdown coordination for asyncio services."""

from __future__ import annotations

import asyncio
import signal
from typing import TYPE_CHECKING

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop
    from collections.abc import Awaitable, Callable, Iterable

logger = get_logger(__name__)


class ShutdownCoordinator:
    """Ensures a shutdown coroutine runs at most once."""

    def __init__(self, shutdown: Callable[[], Awaitable[None]]) -> None:
        self._shutdown = shutdown
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    def request(self) -> None:
        """Request shutdown (fire-and-forget).

        Safe to call multiple times.
        """
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        async with self._lock:
            try:
                await self._shutdown()
            except Exception:
                logger.exception("grpc_shutdown_failed")


def install_signal_handlers(
    loop: AbstractEventLoop,
    coordinator: ShutdownCoordinator,
    *,
    signals: Iterable[signal.Signals] = (signal.SIGINT, signal.SIGTERM),
) -> None:
    """Install OS signal handlers to trigger the provided shutdown coordinator."""
    for sig in signals:
        try:
            loop.add_signal_handler(sig, coordinator.request)
        except NotImplementedError:  # pragma: no cover
            # Windows / limited event loops may not support signal handlers.
            logger.warning("grpc_signal_handlers_unsupported", extra={"signal": str(sig)})
