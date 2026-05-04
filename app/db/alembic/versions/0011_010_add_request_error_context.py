"""Add requests.error_context_json for normalized failure observability snapshots.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    conn = op.get_bind()
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    if "requests" not in tables:
        return
    existing = {row[1] for row in conn.execute(text("PRAGMA table_info('requests')"))}
    if "error_context_json" not in existing:
        op.execute(text("ALTER TABLE requests ADD COLUMN error_context_json TEXT"))


def downgrade() -> None:
    pass
