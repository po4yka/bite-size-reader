"""Database migration CLI tool.

Ensures all tables are created and schema is up to date using the shared
application migration flow.

Usage:
    # Run all migrations (base + versioned)
    python -m app.cli.migrate_db

    # Specify database path
    python -m app.cli.migrate_db /path/to/db.sqlite

    # Show migration status
    python -m app.cli.migrate_db --status [/path/to/db.sqlite]

    # For more migration commands, use the migration runner directly:
    python -m app.cli.migrations.migration_runner status
    python -m app.cli.migrations.migration_runner run --dry-run
"""

from __future__ import annotations

import logging
import sys

from app.cli.migrations.migration_runner import MigrationRunner
from app.core.logging_utils import get_logger
from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)


def _resolve_db_path(args: list[str]) -> str:
    positional = [arg for arg in args if not arg.startswith("-")]
    return positional[0] if positional else "/data/ratatoskr.db"


def _print_status(db: DatabaseSessionManager) -> None:
    runner = MigrationRunner(db)
    status = runner.get_migration_status()
    print("\nMigration Status:")
    print(f"  Total: {status['total']}")
    print(f"  Applied: {status['applied']}")
    print(f"  Pending: {status['pending']}")
    print("\nMigrations:")
    for migration in status["migrations"]:
        status_icon = "✓" if migration["applied"] else "○"
        applied_at = f" (applied {migration['applied_at']})" if migration["applied"] else ""
        print(f"  {status_icon} {migration['name']}{applied_at}")


def main() -> int:
    """Main entry point."""
    args = sys.argv[1:]
    show_status = "--status" in args
    db_path = _resolve_db_path(args)

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    # Initialize database and run migrations
    try:
        db = DatabaseSessionManager(path=db_path)

        if show_status:
            _print_status(db)
            return 0

        logger.info("Running database migrations...")
        db.migrate()
        logger.info("Database migration completed successfully")
        return 0

    except Exception:
        logger.exception("Database migration failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
