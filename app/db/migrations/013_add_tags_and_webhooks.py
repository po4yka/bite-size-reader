"""Add tags, summary_tags, webhook_subscriptions, webhook_deliveries tables."""

from __future__ import annotations

from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import get_logger, log_exception

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)

_TABLES = [
    (
        "tags",
        """
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            color TEXT,
            server_version BIGINT NOT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at DATETIME,
            updated_at DATETIME NOT NULL,
            created_at DATETIME NOT NULL,
            UNIQUE(user_id, normalized_name)
        )
        """,
    ),
    (
        "summary_tags",
        """
        CREATE TABLE IF NOT EXISTS summary_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            summary_id INTEGER NOT NULL REFERENCES summaries(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            source TEXT NOT NULL DEFAULT 'manual',
            server_version BIGINT NOT NULL,
            created_at DATETIME NOT NULL,
            UNIQUE(summary_id, tag_id)
        )
        """,
    ),
    (
        "webhook_subscriptions",
        """
        CREATE TABLE IF NOT EXISTS webhook_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
            name TEXT,
            url TEXT NOT NULL,
            secret TEXT NOT NULL,
            events_json TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'active',
            failure_count INTEGER NOT NULL DEFAULT 0,
            last_delivery_at DATETIME,
            server_version BIGINT NOT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at DATETIME,
            updated_at DATETIME NOT NULL,
            created_at DATETIME NOT NULL
        )
        """,
    ),
    (
        "webhook_deliveries",
        """
        CREATE TABLE IF NOT EXISTS webhook_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL REFERENCES webhook_subscriptions(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            response_status INTEGER,
            response_body TEXT,
            duration_ms INTEGER,
            success INTEGER NOT NULL,
            attempt INTEGER NOT NULL DEFAULT 1,
            error TEXT,
            created_at DATETIME NOT NULL
        )
        """,
    ),
]

_INDEXES = [
    ("idx_tags_user_id", "tags", "user_id"),
    ("idx_summary_tags_tag_id", "summary_tags", "tag_id"),
    ("idx_webhook_subs_user_enabled", "webhook_subscriptions", "user_id, enabled"),
    ("idx_webhook_del_sub_id", "webhook_deliveries", "subscription_id"),
    ("idx_webhook_del_created", "webhook_deliveries", "created_at"),
]


def upgrade(db: DatabaseSessionManager) -> None:
    """Create tags, summary_tags, webhook_subscriptions, webhook_deliveries tables."""
    for table_name, create_sql in _TABLES:
        try:
            db._database.execute_sql(create_sql)
            logger.info("table_created", extra={"table": table_name})
        except peewee.DatabaseError as e:
            log_exception(logger, "table_create_failed", e, table=table_name)
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

    logger.info("migration_013_complete")


def downgrade(db: DatabaseSessionManager) -> None:
    """Drop tags and webhook tables (reverse order for FK safety)."""
    for table_name in ["webhook_deliveries", "webhook_subscriptions", "summary_tags", "tags"]:
        try:
            db._database.execute_sql(f"DROP TABLE IF EXISTS {table_name}")
            logger.info("table_dropped", extra={"table": table_name})
        except peewee.DatabaseError as e:
            log_exception(logger, "table_drop_failed", e, table=table_name)
