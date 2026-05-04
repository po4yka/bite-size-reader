"""Programmatic Alembic runner with cohabitation support for legacy migration_history.

Provides upgrade_to_head() — the single call site used by bootstrap.py and
migrate_db.py.  Existing databases that have migration_history populated (from
the old MigrationRunner) but no alembic_version table are automatically stamped
to head so Alembic skips re-running the historical revisions.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from alembic.config import Config

from app.core.logging_utils import get_logger

logger = get_logger(__name__)

_INI_PATH = str(Path(__file__).resolve().parents[2] / "alembic.ini")


def _build_alembic_config(db_path: str) -> Config:
    from alembic.config import Config

    cfg = Config(_INI_PATH)
    # Override sqlalchemy.url so env.py picks up the correct file path.
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _has_legacy_migration_history(db_path: str) -> bool:
    """Return True if the old MigrationRunner tracking table exists and has rows."""
    if db_path == ":memory:":
        return False
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='migration_history'"
            ).fetchone()
            if not row:
                return False
            count = conn.execute("SELECT COUNT(*) FROM migration_history").fetchone()
            return bool(count and count[0] > 0)
    except Exception:
        return False


def _has_alembic_version(db_path: str) -> bool:
    """Return True if Alembic's alembic_version table already exists."""
    if db_path == ":memory:":
        return False
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            ).fetchone()
            return bool(row)
    except Exception:
        return False


def _stamp_head_sqlite(db_path: str, revision: str) -> None:
    """Write alembic_version directly via sqlite3.

    SQLAlchemy 2.x non-transactional DDL mode for SQLite makes
    context.begin_transaction() a no-op, so command.stamp() leaves the
    INSERT in an uncommitted autobegin transaction.  Using sqlite3 directly
    gives us reliable auto-commit semantics: the with-block commits on exit.
    """
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
        conn.execute("DELETE FROM alembic_version")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES (?)", (revision,))


def upgrade_to_head(db_path: str) -> None:
    """Run all pending Alembic revisions, stamping legacy databases to head first.

    On an existing production database that was managed by the old
    MigrationRunner:
    1. Detect migration_history (legacy) + no alembic_version.
    2. Stamp the database to Alembic head without re-running any revision.
    3. Run upgrade("head") — no-op since we just stamped to head.

    On a fresh database (or one already managed by Alembic):
    1. upgrade("head") runs all pending revisions normally.
    """
    from alembic import command
    from alembic.script import ScriptDirectory

    cfg = _build_alembic_config(db_path)

    if _has_legacy_migration_history(db_path) and not _has_alembic_version(db_path):
        head = ScriptDirectory.from_config(cfg).get_current_head()
        logger.info(
            "alembic_stamp_legacy_db",
            extra={"db_path": _mask(db_path), "head": head},
        )
        _stamp_head_sqlite(db_path, head)
        logger.info("alembic_upgrade_complete", extra={"db_path": _mask(db_path)})
        return  # Stamp puts DB at head; upgrade() would be a no-op and risks not
        # seeing the raw-sqlite3-written row under SA 2.x non-transactional DDL mode.

    command.upgrade(cfg, "head")
    logger.info("alembic_upgrade_complete", extra={"db_path": _mask(db_path)})


def print_status(db_path: str) -> None:
    """Print current Alembic revision and pending migrations to stdout."""
    from alembic import command

    cfg = _build_alembic_config(db_path)
    print("Current revision:")
    command.current(cfg, verbose=True)
    print("\nMigration history:")
    command.history(cfg, verbose=False)


def _mask(path: str) -> str:
    try:
        p = Path(path)
        parent = p.parent.name
        return f".../{parent}/{p.name}" if parent else p.name
    except Exception:
        return "..."
