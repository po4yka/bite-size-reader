"""Registry for Telegram callback action handlers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

CallbackActionHandler = Callable[[Any, int, list[str], str], Awaitable[bool]]


class CallbackActionRegistry:
    """Maps callback action identifiers to async handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, CallbackActionHandler] = {}

    def register(self, action: str, handler: CallbackActionHandler) -> None:
        if not action:
            raise ValueError("Callback action key cannot be empty")
        self._handlers[action] = handler

    def resolve(self, action: str) -> CallbackActionHandler | None:
        return self._handlers.get(action)
