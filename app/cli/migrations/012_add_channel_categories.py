"""Add channel_categories table and category_id FK to channel_subscriptions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import log_exception

if TYPE_CHECKING:
    from app.db.database import Database
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


def upgrade(db: Database | DatabaseSessionManager) -> None:
    """Create channel_categories table and add category_id to channel_subscriptions."""
    # Create channel_categories table
    create_sql = """
    CREATE TABLE IF NOT EXISTS channel_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        position INTEGER NOT NULL DEFAULT 0,
        updated_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL,
        UNIQUE(user_id, name)
    )
    """
    try:
        db._database.execute_sql(create_sql)
        logger.info("table_created", extra={"table": "channel_categories"})
    except peewee.DatabaseError as e:
        log_exception(logger, "table_create_failed", e, table="channel_categories")
        raise

    # Add category_id to channel_subscriptions
    table = "channel_subscriptions"
    column = "category_id"
    try:
        existing = [col.name for col in db._database.get_columns(table)]
        if column not in existing:
            sql = f"ALTER TABLE {table} ADD COLUMN {column} INTEGER REFERENCES channel_categories(id) ON DELETE SET NULL"
            db._database.execute_sql(sql)
            logger.info("column_added", extra={"table": table, "column": column})
        else:
            logger.info("column_exists", extra={"table": table, "column": column})
    except peewee.DatabaseError as e:
        log_exception(logger, "column_add_failed", e, table=table, column=column)
        raise

    logger.info("migration_012_complete")


def downgrade(db: Database | DatabaseSessionManager) -> None:
    """Drop channel_categories table (category_id column stays as SQLite limitation)."""
    try:
        db._database.execute_sql("DROP TABLE IF EXISTS channel_categories")
        logger.info("table_dropped", extra={"table": "channel_categories"})
    except peewee.DatabaseError as e:
        log_exception(logger, "table_drop_failed", e, table="channel_categories")
