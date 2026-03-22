"""Add bot_reply_message_id column to requests table.

Tracks the Telegram message ID of the bot's reply for edit/delete operations.
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
        return False
    try:
        db_instance.execute_sql(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        logger.info("column_added", extra={"table": table, "column": column})
        return True
    except peewee.OperationalError as exc:
        if "duplicate column" in str(exc).lower():
            return False
        raise


def upgrade(db: DatabaseSessionManager) -> None:
    db_instance = getattr(db, "database", getattr(db, "_database", None))
    if db_instance is None:
        msg = "Cannot resolve database instance from db object"
        raise TypeError(msg)

    _add_column(db_instance, "requests", "bot_reply_message_id", "INTEGER")
    logger.info("bot_reply_message_id_migration_complete")


def downgrade(db: DatabaseSessionManager) -> None:
    logger.warning(
        "bot_reply_message_id_downgrade_noop",
        extra={"reason": "SQLite does not support DROP COLUMN"},
    )
