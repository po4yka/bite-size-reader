"""Add columns previously managed by inline _ensure_schema_compatibility().

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None

_COLUMNS = [
    ("requests", "correlation_id", "TEXT"),
    ("summaries", "insights_json", "TEXT"),
    ("summaries", "is_read", "INTEGER"),
    ("crawl_results", "correlation_id", "TEXT"),
    ("crawl_results", "firecrawl_success", "INTEGER"),
    ("crawl_results", "firecrawl_error_code", "TEXT"),
    ("crawl_results", "firecrawl_error_message", "TEXT"),
    ("crawl_results", "firecrawl_details_json", "TEXT"),
    ("llm_calls", "structured_output_used", "INTEGER"),
    ("llm_calls", "structured_output_mode", "TEXT"),
    ("llm_calls", "error_context_json", "TEXT"),
    ("llm_calls", "openrouter_response_text", "TEXT"),
    ("llm_calls", "openrouter_response_json", "TEXT"),
    ("user_interactions", "updated_at", "DATETIME"),
    ("summary_embeddings", "language", "TEXT"),
    ("collections", "parent_id", "INTEGER"),
    ("collections", "position", "INTEGER"),
    ("collections", "is_shared", "INTEGER"),
    ("collections", "share_count", "INTEGER"),
    ("collections", "is_deleted", "INTEGER"),
    ("collections", "deleted_at", "DATETIME"),
    ("collection_items", "position", "INTEGER"),
]


def upgrade() -> None:
    conn = op.get_bind()
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    for table, column, coltype in _COLUMNS:
        if table not in tables:
            continue
        existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info('{table}')"))}
        if column not in existing:
            op.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))


def downgrade() -> None:
    # SQLite <3.35 does not support DROP COLUMN; leave nullable columns in place.
    pass
