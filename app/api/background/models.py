from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int
    base_delay_ms: int
    max_delay_ms: int
    jitter_ratio: float


@dataclass
class LockHandle:
    source: str
    key: str
    token: str | None
    local_lock: asyncio.Lock | None


class StageError(Exception):
    """Wrap a failure with stage context."""

    def __init__(self, stage: str, exc: Exception):
        super().__init__(str(exc))
        self.stage = stage
        self.original = exc
