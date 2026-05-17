"""merge baseline branches 0001b and 0016

Revision ID: 0017_merge
Revises: 0001b, 0016
Create Date: 2026-05-17 10:16:49.847596
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = '0017_merge'
down_revision: str | None = ('0001b', '0016')
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
