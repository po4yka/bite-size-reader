"""SQLAlchemy declarative base for Ratatoskr models."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for SQLAlchemy 2.0 typed declarative models."""
