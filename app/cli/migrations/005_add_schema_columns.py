"""Add columns previously managed by inline _ensure_schema_compatibility().

This migration converts the column additions from schema_migrator.py and
database.py into a proper versioned migration. Each ALTER TABLE is wrapped
in try/except to be idempotent -- existing databases that already have these
columns (from the old inline code) will simply skip them.

Tables and columns added:
- requests: correlation_id
- summaries: insights_json, is_read
- crawl_results: correlation_id, firecrawl_success, firecrawl_error_code,
                  firecrawl_error_message, firecrawl_details_json
- llm_calls: structured_output_used, structured_output_mode,
             error_context_json, openrouter_response_text,
             openrouter_response_json
- user_interactions: updated_at
- summary_embeddings: language
- collections: parent_id, position, is_shared, share_count, is_deleted,
               deleted_at
- collection_items: position
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
    """Add columns that were previously managed by _ensure_schema_compatibility()."""
    db_instance = getattr(db, "database", getattr(db, "_database", None))
    if db_instance is None:
        msg = "Cannot resolve database instance from db object"
        raise TypeError(msg)

    columns = [
        # -- requests --
        ("requests", "correlation_id", "TEXT"),
        # -- summaries --
        ("summaries", "insights_json", "TEXT"),
        ("summaries", "is_read", "INTEGER"),
        # -- crawl_results --
        ("crawl_results", "correlation_id", "TEXT"),
        ("crawl_results", "firecrawl_success", "INTEGER"),
        ("crawl_results", "firecrawl_error_code", "TEXT"),
        ("crawl_results", "firecrawl_error_message", "TEXT"),
        ("crawl_results", "firecrawl_details_json", "TEXT"),
        # -- llm_calls --
        ("llm_calls", "structured_output_used", "INTEGER"),
        ("llm_calls", "structured_output_mode", "TEXT"),
        ("llm_calls", "error_context_json", "TEXT"),
        ("llm_calls", "openrouter_response_text", "TEXT"),
        ("llm_calls", "openrouter_response_json", "TEXT"),
        # -- user_interactions --
        ("user_interactions", "updated_at", "DATETIME"),
        # -- summary_embeddings --
        ("summary_embeddings", "language", "TEXT"),
        # -- collections --
        ("collections", "parent_id", "INTEGER"),
        ("collections", "position", "INTEGER"),
        ("collections", "is_shared", "INTEGER"),
        ("collections", "share_count", "INTEGER"),
        ("collections", "is_deleted", "INTEGER"),
        ("collections", "deleted_at", "DATETIME"),
        # -- collection_items --
        ("collection_items", "position", "INTEGER"),
    ]

    added = 0
    skipped = 0
    for table, column, coltype in columns:
        if _add_column(db_instance, table, column, coltype):
            added += 1
        else:
            skipped += 1

    logger.info(
        "schema_columns_migration_complete",
        extra={"added": added, "skipped": skipped, "total": len(columns)},
    )


def downgrade(db: DatabaseSessionManager) -> None:
    """SQLite does not support DROP COLUMN without table recreation.

    The columns added by this migration are safe to leave in place; they have
    no constraints or defaults that would break older code.  A full downgrade
    would require CREATE TABLE ... AS SELECT (table rebuild) which is
    destructive and risky for production data.
    """
    logger.warning(
        "schema_columns_downgrade_noop",
        extra={"reason": "SQLite does not support DROP COLUMN; manual intervention required"},
    )
