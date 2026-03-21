"""Add automation_rules, rule_execution_logs, and import_jobs tables."""

from __future__ import annotations

from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import get_logger, log_exception

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)

_TABLES = [
    (
        "automation_rules",
        """
        CREATE TABLE IF NOT EXISTS automation_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            event_type TEXT NOT NULL,
            match_mode TEXT NOT NULL DEFAULT 'all',
            conditions_json TEXT NOT NULL DEFAULT '[]',
            actions_json TEXT NOT NULL DEFAULT '[]',
            priority INTEGER NOT NULL DEFAULT 0,
            run_count INTEGER NOT NULL DEFAULT 0,
            last_triggered_at DATETIME,
            server_version BIGINT NOT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at DATETIME,
            updated_at DATETIME NOT NULL,
            created_at DATETIME NOT NULL
        )
        """,
    ),
    (
        "rule_execution_logs",
        """
        CREATE TABLE IF NOT EXISTS rule_execution_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER NOT NULL REFERENCES automation_rules(id) ON DELETE CASCADE,
            summary_id INTEGER REFERENCES summaries(id) ON DELETE SET NULL,
            event_type TEXT NOT NULL,
            matched INTEGER NOT NULL,
            conditions_result_json TEXT,
            actions_taken_json TEXT,
            error TEXT,
            duration_ms INTEGER,
            created_at DATETIME NOT NULL
        )
        """,
    ),
    (
        "import_jobs",
        """
        CREATE TABLE IF NOT EXISTS import_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
            source_format TEXT NOT NULL,
            file_name TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            total_items INTEGER NOT NULL DEFAULT 0,
            processed_items INTEGER NOT NULL DEFAULT 0,
            created_items INTEGER NOT NULL DEFAULT 0,
            skipped_items INTEGER NOT NULL DEFAULT 0,
            failed_items INTEGER NOT NULL DEFAULT 0,
            errors_json TEXT NOT NULL DEFAULT '[]',
            options_json TEXT NOT NULL DEFAULT '{}',
            server_version BIGINT NOT NULL,
            updated_at DATETIME NOT NULL,
            created_at DATETIME NOT NULL
        )
        """,
    ),
]

_INDEXES = [
    ("idx_rules_user_enabled", "automation_rules", "user_id, enabled"),
    ("idx_rules_event_type", "automation_rules", "event_type"),
    ("idx_rule_logs_rule_id", "rule_execution_logs", "rule_id"),
    ("idx_rule_logs_created", "rule_execution_logs", "created_at"),
    ("idx_import_jobs_user", "import_jobs", "user_id"),
    ("idx_import_jobs_status", "import_jobs", "status"),
]


def upgrade(db: DatabaseSessionManager) -> None:
    """Create automation_rules, rule_execution_logs, and import_jobs tables."""
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

    logger.info("migration_015_complete")


def downgrade(db: DatabaseSessionManager) -> None:
    """Drop rule and import tables (reverse order for FK safety)."""
    for table_name in ["import_jobs", "rule_execution_logs", "automation_rules"]:
        try:
            db._database.execute_sql(f"DROP TABLE IF EXISTS {table_name}")
            logger.info("table_dropped", extra={"table": table_name})
        except peewee.DatabaseError as e:
            log_exception(logger, "table_drop_failed", e, table=table_name)
