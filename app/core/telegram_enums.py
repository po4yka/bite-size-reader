"""Compatibility shims for Telegram enums used across the codebase.

Historically these enums lived in ``app.core``. They were moved to
``app.models.telegram`` as part of the modular refactor, but several tests and
legacy imports still reference the old location. This module re-exports the
current definitions to preserve backwards compatibility.
"""

from __future__ import annotations

from app.models.telegram.telegram_enums import ChatType, MediaType, MessageEntityType

__all__ = ["ChatType", "MediaType", "MessageEntityType"]
