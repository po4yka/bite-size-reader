"""Add rss_feeds, rss_feed_subscriptions, rss_feed_items tables."""

from __future__ import annotations

from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import get_logger, log_exception

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)

_TABLES = [
    (
        "rss_feeds",
        """
        CREATE TABLE IF NOT EXISTS rss_feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            title TEXT,
            description TEXT,
            site_url TEXT,
            last_fetched_at DATETIME,
            last_successful_at DATETIME,
            fetch_error_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            etag TEXT,
            last_modified TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            updated_at DATETIME NOT NULL,
            created_at DATETIME NOT NULL
        )
        """,
    ),
    (
        "rss_feed_subscriptions",
        """
        CREATE TABLE IF NOT EXISTS rss_feed_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
            feed_id INTEGER NOT NULL REFERENCES rss_feeds(id) ON DELETE CASCADE,
            category_id INTEGER REFERENCES channel_categories(id) ON DELETE SET NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            updated_at DATETIME NOT NULL,
            created_at DATETIME NOT NULL,
            UNIQUE(user_id, feed_id)
        )
        """,
    ),
    (
        "rss_feed_items",
        """
        CREATE TABLE IF NOT EXISTS rss_feed_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_id INTEGER NOT NULL REFERENCES rss_feeds(id) ON DELETE CASCADE,
            guid TEXT NOT NULL,
            title TEXT,
            url TEXT,
            content TEXT,
            author TEXT,
            published_at DATETIME,
            created_at DATETIME NOT NULL,
            UNIQUE(feed_id, guid)
        )
        """,
    ),
]

_INDEXES = [
    ("idx_rss_subs_user", "rss_feed_subscriptions", "user_id"),
    ("idx_rss_subs_feed", "rss_feed_subscriptions", "feed_id"),
    ("idx_rss_items_published", "rss_feed_items", "published_at"),
    ("idx_rss_items_feed_guid", "rss_feed_items", "feed_id, guid"),
]


def upgrade(db: DatabaseSessionManager) -> None:
    """Create RSS feed tables."""
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

    logger.info("migration_019_complete")


def downgrade(db: DatabaseSessionManager) -> None:
    """Drop RSS feed tables (reverse order for FK safety)."""
    for table_name in ["rss_feed_items", "rss_feed_subscriptions", "rss_feeds"]:
        try:
            db._database.execute_sql(f"DROP TABLE IF EXISTS {table_name}")
            logger.info("table_dropped", extra={"table": table_name})
        except peewee.DatabaseError as e:
            log_exception(logger, "table_drop_failed", e, table=table_name)
