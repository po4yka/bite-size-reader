"""Async collector for Telegram media groups/albums."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class _MediaGroupState(Generic[T]):
    items: list[T] = field(default_factory=list)
    updated_at: float = field(default_factory=time.monotonic)
    done: asyncio.Event = field(default_factory=asyncio.Event)


class MediaGroupCollector(Generic[T]):
    """Collect album items until a quiet period elapses."""

    def __init__(self, *, settle_delay_sec: float = 0.35) -> None:
        self._settle_delay_sec = settle_delay_sec
        self._states: dict[object, _MediaGroupState[T]] = {}
        self._lock = asyncio.Lock()

    async def collect(self, key: object, item: T) -> list[T] | None:
        """Return the settled item list for the owner call, else ``None``."""

        async with self._lock:
            state = self._states.get(key)
            if state is None:
                state = _MediaGroupState(items=[item])
                self._states[key] = state
                owner = True
            else:
                state.items.append(item)
                state.updated_at = time.monotonic()
                owner = False

        if not owner:
            await state.done.wait()
            return None

        try:
            while True:
                await asyncio.sleep(self._settle_delay_sec)
                if time.monotonic() - state.updated_at >= self._settle_delay_sec:
                    break
            return list(state.items)
        finally:
            async with self._lock:
                current = self._states.get(key)
                if current is state:
                    current.done.set()
                    self._states.pop(key, None)


__all__ = ["MediaGroupCollector"]
