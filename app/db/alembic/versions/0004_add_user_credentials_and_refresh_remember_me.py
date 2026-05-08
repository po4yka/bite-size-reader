"""Add user_credentials table and refresh_tokens.remember_me column.

Adds support for nickname/email + password login alongside the existing
Telegram and secret-key auth flows.

* ``user_credentials`` table: one row per user (UNIQUE on user_id) for the
  single-owner deployment. Stores argon2id PHC hashes (the salt + cost params
  travel inside the hash string) plus a ``pepper_version`` so future pepper
  rotations stay backward-compatible. Lockout state mirrors the
  ClientSecret pattern but is independent — locking secret-login must not
  lock credentials login (and vice versa).

* ``refresh_tokens.remember_me`` (BOOLEAN NOT NULL DEFAULT TRUE): preserves
  the chosen TTL family across token rotation. Existing tokens (Telegram /
  secret-login) backfill to TRUE so their 30-day refresh behavior is
  unchanged. Credentials login passes ``remember_me=False`` to issue
  short-lived (12h) refreshes that don't survive browser close.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "user_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("nickname", sa.Text(), nullable=False),
        sa.Column("nickname_canonical", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("email_canonical", sa.Text(), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "pepper_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "failed_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "password_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "server_version",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_credentials_user_id"),
        sa.UniqueConstraint("nickname_canonical", name="uq_user_credentials_nickname_canonical"),
        sa.UniqueConstraint("email_canonical", name="uq_user_credentials_email_canonical"),
    )
    op.create_index(
        "ix_user_credentials_locked_until",
        "user_credentials",
        ["locked_until"],
    )

    op.add_column(
        "refresh_tokens",
        sa.Column(
            "remember_me",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            comment=(
                "When False, refresh-token TTL is the short-lived "
                "credentials-login TTL (e.g., 12h) so it does not survive "
                "browser close. Existing Telegram/secret-login tokens default "
                "to True (30-day TTL family preserved across rotation)."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("refresh_tokens", "remember_me")
    op.drop_index("ix_user_credentials_locked_until", table_name="user_credentials")
    op.drop_table("user_credentials")
