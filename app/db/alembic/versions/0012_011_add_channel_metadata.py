"""Add description and member_count columns to channels table.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | None = None
depends_on: str | None = None

_COLUMNS = [
    ("channels", "description", "TEXT"),
    ("channels", "member_count", "INTEGER"),
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
    pass
