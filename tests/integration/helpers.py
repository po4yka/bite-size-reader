"""Shared helpers for integration tests."""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

from app.cli.migrations.migration_runner import MigrationRunner
from app.db.session import DatabaseSessionManager


@contextmanager
def temp_db() -> Generator[DatabaseSessionManager]:
    """Context manager that creates a temporary SQLite DB, runs all migrations,
    and removes the file on exit.

    Usage::

        with temp_db() as db:
            db._database.execute_sql("SELECT 1")
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db = DatabaseSessionManager(path=db_path)
        db.migrate()
        yield db
    finally:
        Path(db_path).unlink(missing_ok=True)


def run_pending_migrations(db: DatabaseSessionManager) -> int:
    """Run any migrations not yet applied to *db* and return the count applied."""
    runner = MigrationRunner(db)
    return runner.run_pending()
