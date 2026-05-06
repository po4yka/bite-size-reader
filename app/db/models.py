"""SQLAlchemy model export surface.

Model classes are reintroduced in the M-phase port tasks.  F3 keeps this module
importable so infrastructure can target the new SQLAlchemy base while the legacy
Peewee shards are removed.
"""

from __future__ import annotations

from app.db.base import Base

ALL_MODELS: tuple[type[Base], ...] = ()

__all__ = ["ALL_MODELS", "Base"]
