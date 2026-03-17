"""Shared utilities for batch message sending in Telegram adapters."""

from __future__ import annotations

from typing import Any


def is_draft_streaming_enabled(sender: Any) -> bool:
    checker = getattr(sender, "is_draft_streaming_enabled", None)
    if not callable(checker):
        return False
    try:
        result = checker()
    except Exception:
        return False
    return result if isinstance(result, bool) else False


def resolve_sender(formatter: Any) -> Any:
    sender = getattr(formatter, "sender", None)
    return sender if sender is not None else formatter


async def send_message_draft_safe(
    sender: Any,
    message: Any,
    text: str,
    *,
    force: bool = False,
) -> bool:
    send = getattr(sender, "send_message_draft", None)
    if not callable(send):
        return False
    try:
        maybe_awaitable = send(message, text, force=force)
        if hasattr(maybe_awaitable, "__await__"):
            result = await maybe_awaitable
            return bool(result) if isinstance(result, bool) else False
    except Exception:
        return False
    return False
