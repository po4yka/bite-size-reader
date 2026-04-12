"""Add lifecycle timestamps and progress percent to aggregation sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import get_logger, log_exception

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)

_COLUMNS = [
    ("aggregation_sessions", "progress_percent", "INTEGER NOT NULL DEFAULT 0"),
    ("aggregation_sessions", "queued_at", "DATETIME"),
    ("aggregation_sessions", "started_at", "DATETIME"),
    ("aggregation_sessions", "completed_at", "DATETIME"),
    ("aggregation_sessions", "last_progress_at", "DATETIME"),
]


def upgrade(db: DatabaseSessionManager) -> None:
    """Add lifecycle columns and backfill them for existing sessions."""
    for table, column, col_type in _COLUMNS:
        try:
            existing = [col.name for col in db._database.get_columns(table)]
            if column not in existing:
                db._database.execute_sql(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                logger.info("column_added", extra={"table": table, "column": column})
            else:
                logger.info("column_exists", extra={"table": table, "column": column})
        except peewee.DatabaseError as exc:
            log_exception(logger, "column_add_failed", exc, table=table, column=column)
            raise

    try:
        db._database.execute_sql(
            """
            UPDATE aggregation_sessions
            SET
                queued_at = COALESCE(queued_at, created_at),
                last_progress_at = COALESCE(last_progress_at, updated_at),
                progress_percent = CASE
                    WHEN total_items > 0 THEN MIN(
                        100,
                        CAST(
                            ((successful_count + failed_count + duplicate_count) * 100.0)
                            / total_items AS INTEGER
                        )
                    )
                    ELSE 0
                END,
                started_at = CASE
                    WHEN started_at IS NOT NULL THEN started_at
                    WHEN status != 'pending' THEN COALESCE(updated_at, created_at)
                    ELSE NULL
                END,
                completed_at = CASE
                    WHEN completed_at IS NOT NULL THEN completed_at
                    WHEN status IN ('completed', 'partial', 'failed', 'cancelled')
                        THEN COALESCE(updated_at, created_at)
                    ELSE NULL
                END
            """
        )
        logger.info("aggregation_lifecycle_backfilled")
    except peewee.DatabaseError as exc:
        log_exception(logger, "aggregation_lifecycle_backfill_failed", exc)
        raise

    logger.info("migration_022_complete")


def downgrade(db: DatabaseSessionManager) -> None:
    """Lifecycle columns cannot be removed in SQLite (ALTER TABLE limitation)."""
    logger.info("migration_022_downgrade_noop")
