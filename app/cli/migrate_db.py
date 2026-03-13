"""Database migration CLI tool.

Ensures all tables are created and schema is up to date using the shared
application migration flow.

Usage:
    # Run all migrations (base + versioned)
    python -m app.cli.migrate_db

    # Specify database path
    python -m app.cli.migrate_db /path/to/db.sqlite

    # For more migration commands, use the migration runner directly:
    python -m app.cli.migrations.migration_runner status
    python -m app.cli.migrations.migration_runner run --dry-run
"""

from __future__ import annotations

import logging
import sys

from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


def main() -> int:
    """Main entry point."""
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/data/app.db"

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    # Initialize database and run migrations
    try:
        db = DatabaseSessionManager(path=db_path)

        logger.info("Running database migrations...")
        db.migrate()
        logger.info("Database migration completed successfully")
        return 0

    except Exception:
        logger.exception("Database migration failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
