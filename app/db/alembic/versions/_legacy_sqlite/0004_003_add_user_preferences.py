"""Add preferences_json column to users table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = {row[1] for row in conn.execute(text("PRAGMA table_info('users')"))}
    if "preferences_json" not in existing:
        op.execute(text("ALTER TABLE users ADD COLUMN preferences_json TEXT"))


def downgrade() -> None:
    # SQLite <3.35 does not support DROP COLUMN; leave nullable column in place.
    pass
