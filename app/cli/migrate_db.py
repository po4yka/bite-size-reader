"""Database migration CLI tool.

Runs Alembic migrations to bring the schema up to date.  Existing databases
that still have the legacy migration_history table are automatically stamped
to the Alembic head revision so historical migrations are not re-applied.

Usage:
    # Run all pending migrations
    python -m app.cli.migrate_db

    # Specify database path
    python -m app.cli.migrate_db /path/to/db.sqlite

    # Show current revision and pending migrations
    python -m app.cli.migrate_db --status [/path/to/db.sqlite]

    # Use the Alembic CLI directly for full control:
    alembic upgrade head
    alembic downgrade -1
    alembic history
    alembic current
    alembic stamp <revision>
"""

from __future__ import annotations

import logging
import os
import sys

from app.db.alembic_runner import print_status, upgrade_to_head

logger = logging.getLogger(__name__)


def _resolve_db_path(args: list[str]) -> str:
    positional = [arg for arg in args if not arg.startswith("-")]
    return positional[0] if positional else os.getenv("DB_PATH", "/data/ratatoskr.db")


def main() -> int:
    """Main entry point."""
    args = sys.argv[1:]
    show_status = "--status" in args
    db_path = _resolve_db_path(args)

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    try:
        if show_status:
            print_status(db_path)
            return 0

        logger.info("Running database migrations via Alembic...")
        upgrade_to_head(db_path)
        logger.info("Database migration completed successfully")
        return 0

    except Exception:
        logger.exception("Database migration failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
