"""Helpers for reconstructing multiple joined Peewee models from one row."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    import peewee


def aliased_model_fields(model_cls: type[peewee.Model], prefix: str) -> list[Any]:
    """Return model fields aliased with a stable prefix for dict-based joins."""
    return [field.alias(f"{prefix}_{field.name}") for field in model_cls._meta.sorted_fields]


def extract_aliased_model(
    row: Mapping[str, Any],
    model_cls: type[peewee.Model],
    prefix: str,
) -> dict[str, Any] | None:
    """Rebuild a model-shaped dict from a prefixed joined row."""
    primary_key = model_cls._meta.primary_key.name
    if row.get(f"{prefix}_{primary_key}") is None:
        return None

    return {
        field.name: row.get(f"{prefix}_{field.name}") for field in model_cls._meta.sorted_fields
    }
