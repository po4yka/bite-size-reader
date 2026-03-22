"""Types for Telegram command dispatch."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

UidCommandHandler = Callable[[Any, int, str, int, float], Awaitable[None]]
TextCommandHandler = Callable[[Any, str, int, str, int, float], Awaitable[None]]
AliasCommandHandler = Callable[[Any, str, int, str, int, float, str], Awaitable[None]]
SummarizeCommandHandler = Callable[
    [Any, str, int, str, int, float],
    Awaitable[tuple[str | None, bool]],
]


@dataclass(frozen=True, slots=True)
class CommandDispatchOutcome:
    handled: bool
    next_action: str | None = None
