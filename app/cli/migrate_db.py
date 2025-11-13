"""Database migration CLI tool.

Ensures all tables are created and schema is up to date.
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

    # Initialize database and run migration
    try:
        db = Database(path=db_path)
        db.migrate()
        logger.info("Database migration completed successfully")
        return 0
    except Exception:
        logger.exception("Database migration failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
