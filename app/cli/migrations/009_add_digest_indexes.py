"""Add indexes for digest query patterns.

Covers the most common digest-subsystem queries:
- Per-user active subscription lookups
- Bounded delivery history lookback (30-day window)
- Channel post date-based cleanup/queries
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import get_logger, log_exception

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)


def upgrade(db: DatabaseSessionManager) -> None:
    """Add digest-related indexes."""
    indexes = [
        (
            "channel_subscriptions",
            "idx_channel_subs_user_active",
            ["user_id", "is_active"],
            "Speed up per-user active subscription queries",
        ),
        (
            "digest_deliveries",
            "idx_digest_deliveries_user_delivered",
            ["user_id", "delivered_at"],
            "Speed up bounded delivery history lookback",
        ),
        (
            "channel_posts",
            "idx_channel_posts_created_at",
            ["created_at"],
            "Speed up date-based cleanup queries",
        ),
    ]

    created_count = 0
    skipped_count = 0

    for table, index_name, columns, description in indexes:
        try:
            if table not in db._database.get_tables():
                logger.warning(
                    "index_table_missing",
                    extra={"table": table, "index": index_name},
                )
                skipped_count += 1
                continue

            existing_indexes = db._database.get_indexes(table)
            if any(idx.name == index_name for idx in existing_indexes):
                logger.info("index_exists", extra={"index": index_name})
                skipped_count += 1
                continue

            cols = ", ".join(columns)
            sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}({cols})"
            db._database.execute_sql(sql)

            logger.info(
                "index_created",
                extra={"index": index_name, "table": table, "columns": cols},
            )
            logger.debug("index_purpose", extra={"index": index_name, "purpose": description})
            created_count += 1

        except peewee.DatabaseError as e:
            log_exception(
                logger,
                "index_create_failed",
                e,
                index=index_name,
                table=table,
            )
            raise

    logger.info(
        "digest_index_migration_complete",
        extra={"indexes_created": created_count, "indexes_skipped": skipped_count},
    )


def downgrade(db: DatabaseSessionManager) -> None:
    """Remove indexes added by this migration."""
    indexes = [
        "idx_channel_subs_user_active",
        "idx_digest_deliveries_user_delivered",
        "idx_channel_posts_created_at",
    ]

    dropped_count = 0

    for index_name in indexes:
        try:
            db._database.execute_sql(f"DROP INDEX IF EXISTS {index_name}")
            logger.info("index_dropped", extra={"index": index_name})
            dropped_count += 1
        except peewee.DatabaseError as e:
            log_exception(
                logger,
                "index_drop_failed",
                e,
                level="warning",
                index=index_name,
            )

    logger.info("digest_index_rollback_complete", extra={"dropped": dropped_count})
