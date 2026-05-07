"""Tests for the async DatabaseMaintenanceService.

Replaces the legacy sqlite-targeted DatabaseMaintenance test (which
checked `:memory:` skipping and `peewee.DatabaseError` paths). The
current Postgres implementation lives at app.db.runtime.maintenance.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.exc import OperationalError

from app.db.runtime.maintenance import DatabaseMaintenanceService


def _make_service() -> DatabaseMaintenanceService:
    engine = MagicMock()
    session_maker = MagicMock()
    return DatabaseMaintenanceService(
        engine=engine,
        session_maker=session_maker,
        logger=logging.getLogger("test"),
    )


async def test_async_run_analyze_success_returns_true(monkeypatch) -> None:
    service = _make_service()

    class FakeConnection:
        execute = AsyncMock()
        commit = AsyncMock()

    class FakeContextManager:
        async def __aenter__(self) -> FakeConnection:
            return FakeConnection()

        async def __aexit__(self, *_args: Any) -> None:
            return None

    service._engine.connect = MagicMock(return_value=FakeContextManager())

    assert await service.async_run_analyze() is True
    FakeConnection.execute.assert_awaited_once()
    FakeConnection.commit.assert_awaited_once()


async def test_async_run_analyze_failure_returns_false() -> None:
    service = _make_service()

    class FakeConnection:
        async def execute(self, *_args: Any) -> None:
            raise OperationalError("statement", {}, Exception("fail"))

        commit = AsyncMock()

    class FakeContextManager:
        async def __aenter__(self) -> FakeConnection:
            return FakeConnection()

        async def __aexit__(self, *_args: Any) -> None:
            return None

    service._engine.connect = MagicMock(return_value=FakeContextManager())

    assert await service.async_run_analyze() is False


def test_run_startup_maintenance_is_a_noop() -> None:
    """Postgres does not require startup PRAGMA/WAL handling."""
    service = _make_service()
    # Should not raise; logs the skip and returns.
    service.run_startup_maintenance()


def test_run_wal_checkpoint_is_a_noop() -> None:
    """WAL checkpoint is a SQLite concept; the Postgres path returns True."""
    service = _make_service()
    assert service.run_wal_checkpoint() is True
    assert service.run_wal_checkpoint("FULL") is True
