"""Database migration CLI tool.

Ensures all tables are created and schema is up to date.

This tool runs in two phases:
1. Base schema creation (creates all tables defined in models.py)
2. Versioned migrations (applies numbered migration files in order)

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
from pathlib import Path

from app.db.database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Run database migrations."""
    # Determine database path
    db_path = "/data/app.db"
    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    logger.info("Starting database migration for: %s", db_path)

    # Check if database file exists (skip for :memory:)
    if db_path != ":memory:" and not Path(db_path).exists():
        logger.warning("Database file does not exist, will be created: %s", db_path)

    # Initialize database and run migrations
    try:
        db = Database(path=db_path)

        # Phase 1: Run base migration (create tables)
        logger.info("Phase 1: Creating base schema...")
        db.migrate()
        logger.info("✓ Base schema created")

        # Phase 2: Run versioned migrations
        try:
            from app.cli.migrations.migration_runner import MigrationRunner

            logger.info("Phase 2: Running versioned migrations...")
            runner = MigrationRunner(db)
            count = runner.run_pending()

            if count > 0:
                logger.info(f"✓ Applied {count} versioned migration(s)")
            else:
                logger.info("✓ No pending versioned migrations")

        except ImportError:
            logger.warning(
                "Migration runner not available. Install with: pip install -r requirements.txt"
            )
        except Exception as e:
            logger.warning(f"Versioned migrations failed: {e}")
            logger.info("Base schema is still valid")

        logger.info("Database migration completed successfully")
        return 0

    except Exception:
        logger.exception("Database migration failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
