"""Database migration CLI tool.

Runs Alembic migrations to bring the PostgreSQL schema up to date.

Usage:
    # Run all pending migrations
    python -m app.cli.migrate_db

    # Specify database URL
    python -m app.cli.migrate_db postgresql+asyncpg://user:pass@host:5432/db

    # Show current revision and pending migrations
    python -m app.cli.migrate_db --status [DATABASE_URL]

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


def _resolve_dsn(args: list[str]) -> str:
    positional = [arg for arg in args if not arg.startswith("-")]
    return positional[0] if positional else os.getenv("DATABASE_URL", "")


def main() -> int:
    """Main entry point."""
    args = sys.argv[1:]
    show_status = "--status" in args
    dsn = _resolve_dsn(args)

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    try:
        if show_status:
            print_status(dsn or None)
            return 0

        logger.info("Running database migrations via Alembic...")
        upgrade_to_head(dsn or None)
        logger.info("Database migration completed successfully")
        return 0

    except Exception:
        logger.exception("Database migration failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
