"""Add user_backups table for per-user backup archives."""

from __future__ import annotations

from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import get_logger, log_exception

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS user_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    type TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'pending',
    file_path TEXT,
    file_size_bytes INTEGER,
    items_count INTEGER,
    error TEXT,
    server_version BIGINT NOT NULL,
    updated_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL
)
"""

_INDEXES = [
    ("idx_user_backups_user", "user_backups", "user_id"),
    ("idx_user_backups_status", "user_backups", "status"),
]


def upgrade(db: DatabaseSessionManager) -> None:
    """Create user_backups table."""
    try:
        db._database.execute_sql(_CREATE_SQL)
        logger.info("table_created", extra={"table": "user_backups"})
    except peewee.DatabaseError as e:
        log_exception(logger, "table_create_failed", e, table="user_backups")
        raise

    for idx_name, table_name, columns in _INDEXES:
        try:
            db._database.execute_sql(
                f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name}({columns})"
            )
            logger.info("index_created", extra={"index": idx_name, "table": table_name})
        except peewee.DatabaseError as e:
            log_exception(logger, "index_create_failed", e, index=idx_name)
            raise

    logger.info("migration_016_complete")


def downgrade(db: DatabaseSessionManager) -> None:
    """Drop user_backups table."""
    try:
        db._database.execute_sql("DROP TABLE IF EXISTS user_backups")
        logger.info("table_dropped", extra={"table": "user_backups"})
    except peewee.DatabaseError as e:
        log_exception(logger, "table_drop_failed", e, table="user_backups")
