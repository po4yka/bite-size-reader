"""Add scraper-chain attempt log columns to ``crawl_results``.

Per the follow-up of `add-scraper-chain-failure-metrics`, persist the
per-provider attempt log on the row so multi-provider failure paths
are auditable without scraping logs.

  * ``attempt_log`` — JSONB, nullable. Serialized list of
    :class:`ScraperAttemptEntry` dicts in chain order.
  * ``winning_provider`` — text, nullable. Tags the row with the
    provider that produced the successful response, or NULL if the
    chain never returned success.

Backfill-safe: all existing rows get NULL defaults.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str = "0014"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "crawl_results",
        sa.Column("attempt_log", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "crawl_results",
        sa.Column("winning_provider", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("crawl_results", "winning_provider")
    op.drop_column("crawl_results", "attempt_log")
