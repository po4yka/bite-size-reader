"""add github repository tables

Creates the three tables and three Postgres enum types introduced by the
GitHub repository ingestion feature:

* ``repositories``        -- one row per (user, GitHub repo); tracks metadata,
  sync state, and optional LLM analysis.
* ``repository_embeddings`` -- one embedding blob per repository (1:1).
* ``user_github_integrations`` -- one row per user; stores the encrypted PAT /
  OAuth token and sync cursors.

Three Postgres enums are created beforehand and dropped on downgrade:
  repo_source               ('manual', 'starred')
  github_auth_method        ('pat', 'oauth_device')
  github_integration_status ('active', 'needs_reauth', 'revoked')

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

# ---------------------------------------------------------------------------
# Reusable dialect-level enum references (create_type=False so SQLAlchemy
# never auto-emits CREATE TYPE when these appear inside op.create_table).
# The actual CREATE TYPE is emitted explicitly via DO blocks in upgrade().
# ---------------------------------------------------------------------------
_repo_source = postgresql.ENUM("manual", "starred", name="repo_source", create_type=False)
_github_auth_method = postgresql.ENUM(
    "pat", "oauth_device", name="github_auth_method", create_type=False
)
_github_integration_status = postgresql.ENUM(
    "active", "needs_reauth", "revoked", name="github_integration_status", create_type=False
)


def upgrade() -> None:
    # 1. Create the three Postgres enum types via DO blocks.
    #    - postgresql.ENUM.create(bind, checkfirst=True) is unreliable through
    #      the asyncpg sync-bridge (checkfirst query runs but CREATE still fires).
    #    - "CREATE TYPE IF NOT EXISTS" is not valid Postgres SQL syntax.
    #    - DO blocks with a pg_type catalog check are the correct portable pattern.
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'repo_source') THEN
                CREATE TYPE repo_source AS ENUM ('manual', 'starred');
            END IF;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'github_auth_method') THEN
                CREATE TYPE github_auth_method AS ENUM ('pat', 'oauth_device');
            END IF;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'github_integration_status') THEN
                CREATE TYPE github_integration_status AS ENUM ('active', 'needs_reauth', 'revoked');
            END IF;
        END $$
    """)

    # 2. repositories
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("owner", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("full_name", sa.String(length=320), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("homepage_url", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("primary_language", sa.String(length=100), nullable=True),
        sa.Column("languages_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("topics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("forks", sa.Integer(), nullable=False),
        sa.Column("watchers", sa.Integer(), nullable=False),
        sa.Column("default_branch", sa.String(length=100), nullable=True),
        sa.Column("license_spdx", sa.String(length=100), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("is_fork", sa.Boolean(), nullable=False),
        sa.Column("is_template", sa.Boolean(), nullable=False),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at_github", sa.DateTime(timezone=True), nullable=True),
        sa.Column("readme_excerpt", sa.Text(), nullable=True),
        sa.Column("readme_etag", sa.String(length=200), nullable=True),
        sa.Column("analysis_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("analysis_model", sa.String(length=200), nullable=True),
        sa.Column("analysis_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("source", _repo_source, nullable=False),
        sa.Column("is_starred", sa.Boolean(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pending_analysis", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_id"),
        sa.UniqueConstraint("user_id", "github_id", name="uq_repositories_user_github"),
    )
    op.create_index("ix_repositories_github_id", "repositories", ["github_id"], unique=False)
    op.create_index(op.f("ix_repositories_user_id"), "repositories", ["user_id"], unique=False)
    op.create_index(
        "ix_repositories_user_language",
        "repositories",
        ["user_id", "primary_language"],
        unique=False,
    )
    op.create_index(
        "ix_repositories_user_pushed_desc",
        "repositories",
        ["user_id", sa.literal_column("pushed_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_repositories_user_starred",
        "repositories",
        ["user_id", "is_starred"],
        unique=False,
    )

    # 3. user_github_integrations
    op.create_table(
        "user_github_integrations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("auth_method", _github_auth_method, nullable=False),
        sa.Column("encrypted_token", sa.LargeBinary(), nullable=False),
        sa.Column("token_scopes", sa.String(length=500), nullable=True),
        sa.Column("github_login", sa.String(length=100), nullable=True),
        sa.Column("github_user_id", sa.BigInteger(), nullable=True),
        sa.Column("status", _github_integration_status, nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_cursor", sa.String(length=500), nullable=True),
        sa.Column("last_full_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_needs_reauth_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_github_integrations_user_id"),
    )
    op.create_index(
        op.f("ix_user_github_integrations_user_id"),
        "user_github_integrations",
        ["user_id"],
        unique=True,
    )

    # 4. repository_embeddings (FK -> repositories, must come after step 2)
    op.create_table(
        "repository_embeddings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("embedding_blob", sa.LargeBinary(), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repository_id", name="uq_repository_embeddings_repository_id"),
    )
    op.create_index(
        op.f("ix_repository_embeddings_repository_id"),
        "repository_embeddings",
        ["repository_id"],
        unique=True,
    )


def downgrade() -> None:
    # 4. Drop repository_embeddings first (depends on repositories).
    op.drop_index(
        op.f("ix_repository_embeddings_repository_id"), table_name="repository_embeddings"
    )
    op.drop_table("repository_embeddings")

    # 3. Drop user_github_integrations.
    op.drop_index(
        op.f("ix_user_github_integrations_user_id"), table_name="user_github_integrations"
    )
    op.drop_table("user_github_integrations")

    # 2. Drop repositories and its indexes.
    op.drop_index("ix_repositories_user_starred", table_name="repositories")
    op.drop_index("ix_repositories_user_pushed_desc", table_name="repositories")
    op.drop_index("ix_repositories_user_language", table_name="repositories")
    op.drop_index(op.f("ix_repositories_user_id"), table_name="repositories")
    op.drop_index("ix_repositories_github_id", table_name="repositories")
    op.drop_table("repositories")

    # 1. Drop the three Postgres enum types (autogenerate omits these).
    op.execute("DROP TYPE IF EXISTS github_integration_status")
    op.execute("DROP TYPE IF EXISTS github_auth_method")
    op.execute("DROP TYPE IF EXISTS repo_source")
