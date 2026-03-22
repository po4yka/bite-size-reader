"""Shared Peewee model base definitions."""

from __future__ import annotations

import datetime as _dt
from typing import Any

import peewee

from app.core.time_utils import UTC

database_proxy: peewee.Database = peewee.DatabaseProxy()
TOPIC_SEARCH_INDEX_OPTIONS: dict[str, str] = {"tokenize": "unicode61 remove_diacritics 2"}


def _utcnow() -> _dt.datetime:
    """Timezone-aware UTC now (avoids deprecated datetime.utcnow)."""
    return _dt.datetime.now(UTC)


def _next_server_version() -> int:
    """Monotonic-ish server version seed based on current UTC timestamp (ms)."""
    return int(_utcnow().timestamp() * 1000)


class BaseModel(peewee.Model):
    """Base Peewee model bound to the lazily initialised database proxy."""

    def save(self, *args: Any, **kwargs: Any) -> int:
        """Ensure updated_at/server_version fields stay monotonic on every save."""
        now = _utcnow()

        if hasattr(self, "updated_at"):
            self.updated_at = now

        if hasattr(self, "server_version"):
            current = getattr(self, "server_version", 0) or 0
            next_version = int(now.timestamp() * 1000)
            if next_version <= current:
                next_version = current + 1
            self.server_version = next_version
            if hasattr(self, "version"):
                self.version = next_version

        return super().save(*args, **kwargs)

    class Meta:
        database = database_proxy
        legacy_table_names = False


def model_to_dict(model: BaseModel | None) -> dict[str, Any] | None:
    """Convert a Peewee model instance to a plain dictionary."""
    if model is None:
        return None
    data: dict[str, Any] = {}
    for field_name in model._meta.sorted_field_names:
        value = getattr(model, field_name)
        if isinstance(value, peewee.Model):
            value = value.get_id()
        data[field_name] = value
    return data
