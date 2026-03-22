"""Add scope_type and scope_id to user_goals for tag/collection-scoped goals."""

from __future__ import annotations

from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import get_logger, log_exception

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)

_COLUMNS = [
    ("user_goals", "scope_type", "TEXT NOT NULL DEFAULT 'global'"),
    ("user_goals", "scope_id", "INTEGER"),
]


def upgrade(db: DatabaseSessionManager) -> None:
    """Add goal scoping columns."""
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
            "CREATE INDEX IF NOT EXISTS idx_goals_scope "
            "ON user_goals(user_id, goal_type, scope_type, scope_id)"
        )
        logger.info("index_created", extra={"index": "idx_goals_scope"})
    except peewee.DatabaseError as e:
        log_exception(logger, "index_create_failed", e, index="idx_goals_scope")
        raise

    logger.info("migration_018_complete")


def downgrade(db: DatabaseSessionManager) -> None:
    """Goal scoping columns cannot be removed in SQLite (ALTER TABLE limitation)."""
    logger.info("migration_018_downgrade_noop")
