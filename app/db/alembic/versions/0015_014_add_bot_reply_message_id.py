"""Add bot_reply_message_id column to requests table.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "0015"
down_revision: str | None = "0014"
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
    if "bot_reply_message_id" not in existing:
        op.execute(text("ALTER TABLE requests ADD COLUMN bot_reply_message_id INTEGER"))


def downgrade() -> None:
    pass
