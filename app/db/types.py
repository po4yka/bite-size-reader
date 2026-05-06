"""Shared SQLAlchemy model helpers and database-specific types."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

from app.core.time_utils import UTC

JSONValue = dict[str, Any] | list[Any] | str | int | float | bool | None


def _utcnow() -> dt.datetime:
    """Timezone-aware UTC now."""
    return dt.datetime.now(UTC)


def _next_server_version(now: dt.datetime | None = None) -> int:
    """Monotonic-ish server version seed based on UTC timestamp milliseconds."""
    current = now or _utcnow()
    return int(current.timestamp() * 1000)


def model_to_dict(model: object | None) -> dict[str, Any] | None:
    """Convert a SQLAlchemy model instance to a plain dictionary."""
    if model is None:
        return None
    mapper = inspect(model.__class__)
    return {column.key: getattr(model, column.key) for column in mapper.columns}


__all__ = ["JSONB", "TSVECTOR", "JSONValue", "_next_server_version", "_utcnow", "model_to_dict"]
