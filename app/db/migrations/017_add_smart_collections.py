"""Add smart collection fields to collections table."""

from __future__ import annotations

from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import get_logger, log_exception

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)

_COLUMNS = [
    ("collections", "collection_type", "TEXT NOT NULL DEFAULT 'manual'"),
    ("collections", "query_conditions_json", "TEXT"),
    ("collections", "query_match_mode", "TEXT NOT NULL DEFAULT 'all'"),
    ("collections", "last_evaluated_at", "DATETIME"),
]


def upgrade(db: DatabaseSessionManager) -> None:
    """Add smart collection columns to collections table."""
    for table, column, col_type in _COLUMNS:
        try:
            existing = [col.name for col in db._database.get_columns(table)]
            if column not in existing:
                db._database.execute_sql(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                logger.info("column_added", extra={"table": table, "column": column})
            else:
                logger.info("column_exists", extra={"table": table, "column": column})
        except peewee.DatabaseError as e:
            log_exception(logger, "column_add_failed", e, table=table, column=column)
            raise

    try:
        db._database.execute_sql(
            "CREATE INDEX IF NOT EXISTS idx_collections_type ON collections(collection_type)"
        )
        logger.info("index_created", extra={"index": "idx_collections_type"})
    except peewee.DatabaseError as e:
        log_exception(logger, "index_create_failed", e, index="idx_collections_type")
        raise

    logger.info("migration_017_complete")


def downgrade(db: DatabaseSessionManager) -> None:
    """Smart collection columns cannot be removed in SQLite (ALTER TABLE limitation)."""
    logger.info("migration_017_downgrade_noop")
