"""Process-wide pub/sub hub for streaming pipeline events.

Subscribers receive a replay of recent events from a bounded ring buffer, then
live events pushed via asyncio queues.  The hub is designed for low-latency
fan-out from the URL processing pipeline to SSE consumers.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.adapters.content.streaming.events import StreamEvent

_RING_BUFFER_MAXLEN = 64
_QUEUE_MAXSIZE = 128
_CLEANUP_TTL_SECONDS = 60
_TERMINAL_KINDS = frozenset({"done", "error"})


class StreamHub:
    """In-process asyncio pub/sub. Not thread-safe; single-process only."""

    def __init__(self) -> None:
        self._buffers: dict[str, deque[StreamEvent]] = {}
        self._subscribers: dict[str, list[asyncio.Queue[StreamEvent]]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    def publish(self, request_id: str, event: StreamEvent) -> None:
        logger.bind(request_id=request_id).debug(
            "stream.publish",
            kind=event.kind,
            correlation_id=event.correlation_id,
        )

        if request_id not in self._buffers:
            self._buffers[request_id] = deque(maxlen=_RING_BUFFER_MAXLEN)
        self._buffers[request_id].append(event)

        for queue in self._subscribers.get(request_id, []):
            self._put_event(queue, event)

        if event.kind in _TERMINAL_KINDS:
            self._schedule_cleanup(request_id)

    async def subscribe(self, request_id: str) -> AsyncIterator[StreamEvent]:
        queue: asyncio.Queue[StreamEvent] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)

        # Snapshot backlog before registering — single-threaded asyncio guarantees
        # no publish can interleave between the snapshot and the queue attach.
        backlog = list(self._buffers.get(request_id, []))

        async with self._lock:
            self._subscribers.setdefault(request_id, []).append(queue)

        logger.bind(request_id=request_id).debug(
            "stream.subscribe",
            backlog_len=len(backlog),
        )

        try:
            for event in backlog:
                yield event
                if event.kind in _TERMINAL_KINDS:
                    return

            while True:
                event = await queue.get()
                yield event
                if event.kind in _TERMINAL_KINDS:
                    return

        finally:
            logger.bind(request_id=request_id).debug("stream.disconnect")
            async with self._lock:
                subs = self._subscribers.get(request_id)
                if subs is not None and queue in subs:
                    subs.remove(queue)

    @staticmethod
    def _put_event(queue: asyncio.Queue[StreamEvent], event: StreamEvent) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            dropped = _drop_oldest_non_terminal(queue)
            if dropped is not None or event.kind in _TERMINAL_KINDS:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    def _schedule_cleanup(self, request_id: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (sync test context).
            self._cleanup_request(request_id)
            return
        loop.call_later(_CLEANUP_TTL_SECONDS, self._cleanup_request, request_id)

    def _cleanup_request(self, request_id: str) -> None:
        self._buffers.pop(request_id, None)
        self._subscribers.pop(request_id, None)


def _drop_oldest_non_terminal(queue: asyncio.Queue[StreamEvent]) -> StreamEvent | None:
    # Direct ``queue._queue`` access is a CPython internal but stable across
    # 3.x; tested under 3.13. Avoids the cost/complexity of draining + refilling.
    inner: deque[StreamEvent] = queue._queue  # type: ignore[attr-defined]
    for i, item in enumerate(inner):
        if item.kind not in _TERMINAL_KINDS:
            del inner[i]
            return item
    return None


_hub: StreamHub | None = None


def get_stream_hub() -> StreamHub:
    global _hub
    if _hub is None:
        _hub = StreamHub()
    return _hub


__all__ = [
    "StreamHub",
    "get_stream_hub",
]
