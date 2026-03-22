"""Typing-only base for SQLite repository mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.infrastructure.persistence.sqlite.base import (
        SqliteBaseRepository as SqliteRepositoryMixinBase,
    )
else:

    class SqliteRepositoryMixinBase:
        """Runtime no-op base used only to satisfy mixin type checking."""


__all__ = ["SqliteRepositoryMixinBase"]
