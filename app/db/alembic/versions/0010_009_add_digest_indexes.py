"""Add indexes for digest query patterns.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None

_INDEXES = [
    ("channel_subscriptions", "idx_channel_subs_user_active", "user_id, is_active"),
    ("digest_deliveries", "idx_digest_deliveries_user_delivered", "user_id, delivered_at"),
    ("channel_posts", "idx_channel_posts_created_at", "created_at"),
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
