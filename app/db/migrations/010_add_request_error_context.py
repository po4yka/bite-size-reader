"""Add structured request error context snapshot column.

Adds requests.error_context_json for normalized failure observability snapshots.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)


def _add_column(
    db_instance: peewee.SqliteDatabase,
    table: str,
    column: str,
    coltype: str,
) -> bool:
    if table not in db_instance.get_tables():
        logger.debug("table_not_found", extra={"table": table, "column": column})
        return False
    try:
        db_instance.execute_sql(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        logger.info("column_added", extra={"table": table, "column": column, "type": coltype})
        return True
    except peewee.OperationalError as exc:
        if "duplicate column" in str(exc).lower():
            logger.debug("column_exists", extra={"table": table, "column": column})
            return False
        raise


def upgrade(db: DatabaseSessionManager) -> None:
    """Add requests.error_context_json."""
    db_instance = getattr(db, "database", getattr(db, "_database", None))
    if db_instance is None:
        msg = "Cannot resolve database instance from db object"
        raise TypeError(msg)

    added = _add_column(db_instance, "requests", "error_context_json", "TEXT")
    logger.info(
        "request_error_context_migration_complete",
        extra={"added": int(added), "skipped": int(not added)},
    )


def downgrade(db: DatabaseSessionManager) -> None:
    """Downgrade is a no-op due SQLite drop-column limitations."""
    logger.warning(
        "request_error_context_downgrade_noop",
        extra={"reason": "SQLite does not support DROP COLUMN safely"},
    )
