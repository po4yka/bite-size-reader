"""Add description and member_count columns to channels table."""

from __future__ import annotations

from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import get_logger, log_exception

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)


def upgrade(db: DatabaseSessionManager) -> None:
    """Add description and member_count to channels."""
    columns = [
        ("channels", "description", "TEXT"),
        ("channels", "member_count", "INTEGER"),
    ]

    for table, column, col_type in columns:
        try:
            if table not in db._database.get_tables():
                logger.warning("table_missing", extra={"table": table})
                continue

            existing = [col.name for col in db._database.get_columns(table)]
            if column in existing:
                logger.info("column_exists", extra={"table": table, "column": column})
                continue

            sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
            db._database.execute_sql(sql)
            logger.info("column_added", extra={"table": table, "column": column})

        except peewee.DatabaseError as e:
            log_exception(logger, "column_add_failed", e, table=table, column=column)
            raise

    logger.info("migration_011_complete")


def downgrade(db: DatabaseSessionManager) -> None:
    """SQLite does not support DROP COLUMN before 3.35.0; recreate if needed."""
    logger.warning("migration_011_downgrade_noop")
