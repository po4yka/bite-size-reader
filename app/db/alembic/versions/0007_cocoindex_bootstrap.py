"""CocoIndex bootstrap: schema and summary_embeddings index columns.

Creates the dedicated `cocoindex` schema (for CocoIndex's own bookkeeping
tables) and adds content_hash, last_indexed_at, and index_status columns
to summary_embeddings for idempotency tracking.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create dedicated schema for CocoIndex bookkeeping tables
    op.execute("CREATE SCHEMA IF NOT EXISTS cocoindex")

    # Add index tracking columns to summary_embeddings
    op.add_column(
        "summary_embeddings",
        sa.Column("content_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "summary_embeddings",
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "summary_embeddings",
        sa.Column(
            "index_status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
    )
    op.create_index(
        "ix_summary_embeddings_last_indexed_at",
        "summary_embeddings",
        ["last_indexed_at"],
    )

    # Grant privileges so CocoIndex can create its bookkeeping tables
    # and install LISTEN/NOTIFY triggers on summaries.
    # Use DO block to handle case where role doesn't exist gracefully.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ratatoskr') THEN
                GRANT USAGE, CREATE ON SCHEMA cocoindex TO ratatoskr;
                GRANT TRIGGER ON summaries TO ratatoskr;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_summary_embeddings_last_indexed_at", table_name="summary_embeddings")
    op.drop_column("summary_embeddings", "index_status")
    op.drop_column("summary_embeddings", "last_indexed_at")
    op.drop_column("summary_embeddings", "content_hash")
    op.execute("DROP SCHEMA IF EXISTS cocoindex CASCADE")
