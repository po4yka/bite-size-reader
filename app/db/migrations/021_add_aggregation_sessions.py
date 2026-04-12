"""Add aggregation session storage tables."""

from __future__ import annotations

from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import get_logger, log_exception

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)

_TABLES = [
    (
        "aggregation_sessions",
        """
        CREATE TABLE IF NOT EXISTS aggregation_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
            correlation_id TEXT NOT NULL UNIQUE,
            total_items INTEGER NOT NULL,
            successful_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            allow_partial_success INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'pending',
            bundle_metadata_json JSON,
            aggregation_output_json JSON,
            failure_code TEXT,
            failure_message TEXT,
            failure_details_json JSON,
            processing_time_ms INTEGER,
            server_version INTEGER NOT NULL DEFAULT 1,
            updated_at DATETIME NOT NULL,
            created_at DATETIME NOT NULL
        )
        """,
    ),
    (
        "aggregation_session_items",
        """
        CREATE TABLE IF NOT EXISTS aggregation_session_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aggregation_session_id INTEGER NOT NULL REFERENCES aggregation_sessions(id) ON DELETE CASCADE,
            request_id INTEGER REFERENCES requests(id) ON DELETE SET NULL,
            position INTEGER NOT NULL,
            source_kind TEXT NOT NULL,
            source_item_id TEXT NOT NULL,
            source_dedupe_key TEXT NOT NULL,
            original_value TEXT,
            normalized_value TEXT,
            external_id TEXT,
            telegram_chat_id INTEGER,
            telegram_message_id INTEGER,
            telegram_media_group_id TEXT,
            title_hint TEXT,
            source_metadata_json JSON,
            normalized_document_json JSON,
            extraction_metadata_json JSON,
            status TEXT NOT NULL DEFAULT 'pending',
            duplicate_of_item_id INTEGER,
            failure_code TEXT,
            failure_message TEXT,
            failure_details_json JSON,
            updated_at DATETIME NOT NULL,
            created_at DATETIME NOT NULL
        )
        """,
    ),
]

_INDEXES = [
    ("idx_aggregation_sessions_user", "aggregation_sessions", "user_id"),
    ("idx_aggregation_sessions_status", "aggregation_sessions", "status"),
    ("idx_aggregation_sessions_created", "aggregation_sessions", "created_at"),
    (
        "idx_aggregation_session_items_position",
        "aggregation_session_items",
        "aggregation_session_id, position",
    ),
    (
        "idx_aggregation_session_items_source_item",
        "aggregation_session_items",
        "aggregation_session_id, source_item_id",
    ),
    ("idx_aggregation_session_items_request", "aggregation_session_items", "request_id"),
    ("idx_aggregation_session_items_status", "aggregation_session_items", "status"),
    (
        "idx_aggregation_session_items_duplicate_of",
        "aggregation_session_items",
        "duplicate_of_item_id",
    ),
]


def upgrade(db: DatabaseSessionManager) -> None:
    """Create aggregation session tables and indexes."""
    for table_name, create_sql in _TABLES:
        try:
            db._database.execute_sql(create_sql)
            logger.info("table_created", extra={"table": table_name})
        except peewee.DatabaseError as exc:
            log_exception(logger, "table_create_failed", exc, table=table_name)
            raise

    for index_name, table_name, columns in _INDEXES:
        try:
            unique = " UNIQUE" if index_name.endswith("_position") else ""
            db._database.execute_sql(
                f"CREATE{unique} INDEX IF NOT EXISTS {index_name} ON {table_name}({columns})"
            )
            logger.info("index_created", extra={"index": index_name, "table": table_name})
        except peewee.DatabaseError as exc:
            log_exception(logger, "index_create_failed", exc, index=index_name)
            raise

    logger.info("migration_021_complete")


def downgrade(db: DatabaseSessionManager) -> None:
    """Drop aggregation session tables."""
    for table_name in ["aggregation_session_items", "aggregation_sessions"]:
        try:
            db._database.execute_sql(f"DROP TABLE IF EXISTS {table_name}")
            logger.info("table_dropped", extra={"table": table_name})
        except peewee.DatabaseError as exc:
            log_exception(logger, "table_drop_failed", exc, table=table_name)
            raise
