"""Add performance indexes to improve query speed.

This migration adds indexes for the most common query patterns:
- Correlation ID lookups (debugging)
- User/chat history (pagination)
- Status filtering (monitoring)
- Unread summaries (user feature)
- LLM call tracking (cost analysis)

Expected impact: 10-100x speedup on indexed queries.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import log_exception

if TYPE_CHECKING:
    from app.db.database import Database

logger = logging.getLogger(__name__)


def upgrade(db: Database) -> None:
    """Add performance indexes."""
    indexes = [
        # Request table indexes
        (
            "requests",
            "idx_requests_correlation_id",
            ["correlation_id"],
            "Speed up correlation ID lookups during debugging",
        ),
        (
            "requests",
            "idx_requests_user_created",
            ["user_id", "created_at"],
            "Speed up user history queries with date sorting",
        ),
        (
            "requests",
            "idx_requests_chat_created",
            ["chat_id", "created_at"],
            "Speed up chat history queries with date sorting",
        ),
        (
            "requests",
            "idx_requests_status_type",
            ["status", "type", "created_at"],
            "Speed up status filtering for monitoring",
        ),
        (
            "requests",
            "idx_requests_normalized_url",
            ["normalized_url"],
            "Speed up URL deduplication checks",
        ),
        # Summary table indexes
        (
            "summaries",
            "idx_summaries_read_status",
            ["is_read", "created_at"],
            "Speed up unread summary queries",
        ),
        (
            "summaries",
            "idx_summaries_lang",
            ["lang", "created_at"],
            "Speed up language-specific queries",
        ),
        # LLMCall table indexes
        (
            "llm_calls",
            "idx_llm_calls_request",
            ["request_id", "created_at"],
            "Speed up LLM call lookups by request",
        ),
        (
            "llm_calls",
            "idx_llm_calls_status",
            ["status", "created_at"],
            "Speed up error monitoring queries",
        ),
        (
            "llm_calls",
            "idx_llm_calls_model",
            ["model", "created_at"],
            "Speed up cost analysis by model",
        ),
        (
            "llm_calls",
            "idx_llm_calls_provider_model",
            ["provider", "model", "created_at"],
            "Speed up provider-specific queries",
        ),
        # CrawlResult table indexes (no timestamp column)
        (
            "crawl_results",
            "idx_crawl_results_status",
            ["status"],
            "Speed up Firecrawl error monitoring",
        ),
        (
            "crawl_results",
            "idx_crawl_results_source_url",
            ["source_url"],
            "Speed up URL-based crawl lookups",
        ),
        # AuditLog table indexes
        (
            "audit_logs",
            "idx_audit_logs_level_ts",
            ["level", "ts"],
            "Speed up log filtering by severity",
        ),
        (
            "audit_logs",
            "idx_audit_logs_event_ts",
            ["event", "ts"],
            "Speed up event-specific log queries",
        ),
    ]

    created_count = 0
    skipped_count = 0

    for table, index_name, columns, description in indexes:
        try:
            # Check if table exists
            if table not in db._database.get_tables():
                logger.warning(
                    "index_table_missing",
                    extra={"table": table, "index": index_name},
                )
                skipped_count += 1
                continue

            # Check if index already exists
            existing_indexes = db._database.get_indexes(table)
            if any(idx.name == index_name for idx in existing_indexes):
                logger.info("index_exists", extra={"index": index_name})
                skipped_count += 1
                continue

            # Create index
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
        "index_migration_complete",
        extra={"indexes_created": created_count, "indexes_skipped": skipped_count},
    )


def downgrade(db: Database) -> None:
    """Remove indexes added by this migration."""
    indexes = [
        "idx_requests_correlation_id",
        "idx_requests_user_created",
        "idx_requests_chat_created",
        "idx_requests_status_type",
        "idx_requests_normalized_url",
        "idx_summaries_read_status",
        "idx_summaries_lang",
        "idx_llm_calls_request",
        "idx_llm_calls_status",
        "idx_llm_calls_model",
        "idx_llm_calls_provider_model",
        "idx_crawl_results_status",
        "idx_crawl_results_source_url",
        "idx_audit_logs_level_ts",
        "idx_audit_logs_event_ts",
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

    logger.info("index_rollback_complete", extra={"dropped": dropped_count})
