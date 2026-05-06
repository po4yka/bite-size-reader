"""SQLAlchemy declarative base for Ratatoskr models."""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import DeclarativeBase

from app.db.types import _next_server_version, _utcnow


class Base(DeclarativeBase):
    """Base class for SQLAlchemy 2.0 typed declarative models."""


@event.listens_for(Base, "before_update", propagate=True)
def _update_timestamps_and_server_version(_mapper: Any, _connection: Any, target: Any) -> None:
    now = _utcnow()
    if hasattr(target, "updated_at"):
        target.updated_at = now
    if hasattr(target, "server_version"):
        current = getattr(target, "server_version", 0) or 0
        next_version = _next_server_version(now)
        if next_version <= current:
            next_version = current + 1
        target.server_version = next_version
