"""Add channel_categories table and category_id FK to channel_subscriptions.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    conn = op.get_bind()
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    if "channel_categories" not in tables:
        op.execute(
            text("""
            CREATE TABLE IF NOT EXISTS channel_categories (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
                name       TEXT NOT NULL,
                position   INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME NOT NULL,
                created_at DATETIME NOT NULL,
                UNIQUE(user_id, name)
            )
        """)
        )

    if "channel_subscriptions" in tables:
        existing = {
            row[1] for row in conn.execute(text("PRAGMA table_info('channel_subscriptions')"))
        }
        if "category_id" not in existing:
            op.execute(
                text(
                    "ALTER TABLE channel_subscriptions ADD COLUMN category_id INTEGER"
                    " REFERENCES channel_categories(id) ON DELETE SET NULL"
                )
            )


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS channel_categories"))
