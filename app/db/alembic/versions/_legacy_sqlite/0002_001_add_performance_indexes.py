"""Add performance indexes to improve query speed.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None

_INDEXES = [
    ("requests", "idx_requests_correlation_id", "correlation_id"),
    ("requests", "idx_requests_user_created", "user_id, created_at"),
    ("requests", "idx_requests_chat_created", "chat_id, created_at"),
    ("requests", "idx_requests_status_type", "status, type, created_at"),
    ("requests", "idx_requests_normalized_url", "normalized_url"),
    ("summaries", "idx_summaries_read_status", "is_read, created_at"),
    ("summaries", "idx_summaries_lang", "lang, created_at"),
    ("llm_calls", "idx_llm_calls_request", "request_id, created_at"),
    ("llm_calls", "idx_llm_calls_status", "status, created_at"),
    ("llm_calls", "idx_llm_calls_model", "model, created_at"),
    ("llm_calls", "idx_llm_calls_provider_model", "provider, model, created_at"),
    ("crawl_results", "idx_crawl_results_status", "status"),
    ("crawl_results", "idx_crawl_results_source_url", "source_url"),
    ("audit_logs", "idx_audit_logs_level_ts", "level, ts"),
    ("audit_logs", "idx_audit_logs_event_ts", "event, ts"),
]


def upgrade() -> None:
    conn = op.get_bind()
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    for table, idx_name, cols in _INDEXES:
        if table not in tables:
            continue
        existing = {row[1] for row in conn.execute(text(f"PRAGMA index_list('{table}')"))}
        if idx_name not in existing:
            op.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({cols})"))


def downgrade() -> None:
    for _table, idx_name, _cols in _INDEXES:
        op.execute(text(f"DROP INDEX IF EXISTS {idx_name}"))
