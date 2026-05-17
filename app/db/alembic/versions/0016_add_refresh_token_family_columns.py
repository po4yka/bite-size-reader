"""Add token-family columns to ``refresh_tokens``.

Per the follow-up of `harden-refresh-token-rotation-revocation`,
back the in-memory :class:`TokenFamilyPolicy` decision module with
the schema it expects.

  * ``family_id`` — text, NOT NULL. Every refresh token belongs to
    a family; rotation issues a new token in the same family; reuse
    of a retired token revokes the entire family.
  * ``parent_token_hash`` — text, nullable. NULL for the root token
    of each family; populated with the hash of the predecessor
    after a rotation.

Backfill: existing rows each get a unique ``family_id`` (UUID4) so
the not-null constraint is satisfied without coupling historical
tokens into shared families. ``parent_token_hash`` is left NULL
(treated as the root).

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str = "0015"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    # 1. Add columns as nullable so we can backfill safely.
    op.add_column(
        "refresh_tokens",
        sa.Column("family_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("parent_token_hash", sa.Text(), nullable=True),
    )
    # 2. Backfill every existing row with its own unique family_id
    # using Postgres' built-in gen_random_uuid() (pgcrypto) cast to
    # text. Each historical token becomes a singleton family —
    # matches today's no-rotation behaviour.
    op.execute(
        "UPDATE refresh_tokens SET family_id = gen_random_uuid()::text WHERE family_id IS NULL"
    )
    # 3. Promote family_id to NOT NULL once backfilled.
    op.alter_column("refresh_tokens", "family_id", nullable=False)
    op.create_index(
        "ix_refresh_tokens_family_id",
        "refresh_tokens",
        ["family_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "parent_token_hash")
    op.drop_column("refresh_tokens", "family_id")
