"""Baseline: represents the schema state after all 15 legacy migrations.

Existing databases that have migration_history populated are stamped to
this revision so Alembic skips the historical 0002-0016 revisions.

Revision ID: 0001
Revises: None
Create Date: 2026-05-04
"""

from __future__ import annotations

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
