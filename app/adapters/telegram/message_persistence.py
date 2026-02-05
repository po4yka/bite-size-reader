"""Backwards-compatible re-export.

MessagePersistence is adapter-agnostic (no Telegram-specific types) and now
lives in app.infrastructure.persistence.message_persistence.  This shim
re-exports the class so that existing imports from this path continue to work.
"""

from app.infrastructure.persistence.message_persistence import MessagePersistence

__all__ = ["MessagePersistence"]
