"""Add error tracking fields to requests table.

This migration adds error_type, error_message, error_timestamp, and
processing_time_ms fields to the requests table for batch URL processing
persistence. This ensures all URLs get database records even if processing
fails early in the batch loop.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import peewee

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


def _add_column(
    db_instance: peewee.SqliteDatabase,
    table: str,
    column: str,
    coltype: str,
) -> bool:
    """Add a column to a table, returning True if added, False if it already exists."""
    if table not in db_instance.get_tables():
        logger.debug("table_not_found", extra={"table": table, "column": column})
        return False
    try:
        db_instance.execute_sql(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        logger.info("column_added", extra={"table": table, "column": column, "type": coltype})
        return True
    except peewee.OperationalError as exc:
        # SQLite raises OperationalError if column already exists
        if "duplicate column" in str(exc).lower():
            logger.debug("column_exists", extra={"table": table, "column": column})
            return False
        raise


def upgrade(db: DatabaseSessionManager) -> None:
    """Add error tracking columns to requests table."""
    db_instance = getattr(db, "database", getattr(db, "_database", None))
    if db_instance is None:
        msg = "Cannot resolve database instance from db object"
        raise TypeError(msg)

    columns = [
        ("requests", "error_type", "TEXT"),
        ("requests", "error_message", "TEXT"),
        ("requests", "error_timestamp", "DATETIME"),
        ("requests", "processing_time_ms", "INTEGER"),
    ]

    added = 0
    skipped = 0
    for table, column, coltype in columns:
        if _add_column(db_instance, table, column, coltype):
            added += 1
        else:
            skipped += 1

    logger.info(
        "request_error_fields_migration_complete",
        extra={"added": added, "skipped": skipped, "total": len(columns)},
    )


def downgrade(db: DatabaseSessionManager) -> None:
    """Remove error tracking columns from requests table.

    Note: SQLite doesn't support DROP COLUMN in older versions.
    This is a no-op for safety; columns can remain nullable.
    """
    logger.warning(
        "request_error_fields_downgrade_noop",
        extra={"reason": "SQLite does not support DROP COLUMN; manual intervention required"},
    )
