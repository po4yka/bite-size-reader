"""Backwards-compatible re-export.

MessagePersistence is adapter-agnostic (no Telegram-specific types) and now
lives in app.infrastructure.persistence.message_persistence.  This shim
re-exports the class so that existing imports from this path continue to work.
"""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name != "MessagePersistence":
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    from app.infrastructure.persistence.message_persistence import MessagePersistence

    globals()[name] = MessagePersistence
    return MessagePersistence
