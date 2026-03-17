"""Tests for DatabaseMaintenance."""

from __future__ import annotations

from unittest.mock import MagicMock

import peewee

from app.db.database_maintenance import DatabaseMaintenance


def _make_maintenance(path: str = "/data/app.db") -> DatabaseMaintenance:
    db = MagicMock()
    db.connection_context.return_value.__enter__ = MagicMock(return_value=None)
    db.connection_context.return_value.__exit__ = MagicMock(return_value=False)
    return DatabaseMaintenance(db, path)


def test_run_maintenance_skips_in_memory() -> None:
    db = MagicMock()
    maint = DatabaseMaintenance(db, ":memory:")
    result = maint.run_maintenance()
    assert result["status"] == "skipped"
    db.execute_sql.assert_not_called()


def test_run_analyze_success() -> None:
    maint = _make_maintenance()
    result = maint.run_analyze()
    assert result is True
    maint._database.execute_sql.assert_called_once_with("ANALYZE;")


def test_run_analyze_failure() -> None:
    maint = _make_maintenance()
    maint._database.execute_sql.side_effect = peewee.DatabaseError("fail")
    result = maint.run_analyze()
    assert result is False


def test_run_vacuum_success() -> None:
    maint = _make_maintenance()
    result = maint.run_vacuum()
    assert result is True
    maint._database.execute_sql.assert_called_once_with("VACUUM;")


def test_run_wal_checkpoint_invalid_mode() -> None:
    maint = _make_maintenance()
    result = maint.run_wal_checkpoint(mode="INVALID")
    assert result is False
    maint._database.execute_sql.assert_not_called()


def test_run_wal_checkpoint_valid_modes() -> None:
    for mode in ("PASSIVE", "FULL", "RESTART", "TRUNCATE"):
        maint = _make_maintenance()
        result = maint.run_wal_checkpoint(mode=mode)
        assert result is True
        maint._database.execute_sql.assert_called_once_with(
            f"PRAGMA wal_checkpoint({mode.upper()});"
        )


def test_run_maintenance_partial_on_failure() -> None:
    maint = _make_maintenance()
    # First call (ANALYZE) succeeds, second call (VACUUM) fails
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise peewee.DatabaseError("vacuum failed")

    maint._database.execute_sql.side_effect = side_effect
    result = maint.run_maintenance()
    assert result["status"] == "partial"
    assert result["operations"]["analyze"] == "success"
    assert result["operations"]["vacuum"] == "failed"
