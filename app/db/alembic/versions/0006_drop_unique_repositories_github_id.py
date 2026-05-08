"""drop unique constraint on repositories.github_id

The table-level UniqueConstraint("github_id") emitted by migration 0005
prevents two different users from starring the same GitHub repository.
The correct uniqueness boundary is the composite (user_id, github_id),
already enforced by uq_repositories_user_github.

This migration drops the redundant table-level unique constraint and
ensures the plain index ix_repositories_github_id (already created in
0005) is present for sync-lookup performance.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    # Drop the table-level unique constraint added by migration 0005.
    # Postgres default name for UniqueConstraint("github_id") on table
    # "repositories" is "repositories_github_id_key".
    # Guard with DO block for idempotency (e.g. already run on a DB where
    # 0005 was applied without the unique constraint).
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'repositories_github_id_key'
                  AND conrelid = 'repositories'::regclass
                  AND contype = 'u'
            ) THEN
                ALTER TABLE repositories DROP CONSTRAINT repositories_github_id_key;
            END IF;
        END $$
    """)

    # Ensure the named non-unique index exists (0005 already creates it;
    # this is a no-op on a live DB but keeps the migration self-contained).
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_repositories_github_id
        ON repositories (github_id)
    """)


def downgrade() -> None:
    # Restore the (incorrect) table-level unique constraint.
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'repositories_github_id_key'
                  AND conrelid = 'repositories'::regclass
            ) THEN
                ALTER TABLE repositories
                    ADD CONSTRAINT repositories_github_id_key UNIQUE (github_id);
            END IF;
        END $$
    """)
    # The ix_repositories_github_id index created in 0005 is kept; it
    # becomes redundant once the unique constraint is back but is harmless.
