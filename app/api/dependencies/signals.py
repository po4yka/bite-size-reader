"""Signal API dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request  # noqa: TC002 - FastAPI requires the concrete type at runtime.

from app.api.dependencies.database import get_session_manager
from app.di.api import resolve_api_runtime
from app.infrastructure.persistence.repositories.signal_source_repository import (
    SqliteSignalSourceRepositoryAdapter,
)

if TYPE_CHECKING:
    from app.application.ports.signal_sources import SignalSourceRepositoryPort


def get_signal_source_repository(request: Request) -> SignalSourceRepositoryPort:
    """Resolve the signal source repository for API handlers."""
    try:
        db = resolve_api_runtime(request).db
    except RuntimeError:
        db = get_session_manager(request)
    return SqliteSignalSourceRepositoryAdapter(db)
