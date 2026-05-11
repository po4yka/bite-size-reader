"""Grant CocoIndex trigger access for repository indexing.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op

revision: str = "0008"
down_revision: str = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ratatoskr') THEN
                GRANT TRIGGER ON repositories TO ratatoskr;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ratatoskr') THEN
                REVOKE TRIGGER ON repositories FROM ratatoskr;
            END IF;
        END
        $$;
        """
    )
