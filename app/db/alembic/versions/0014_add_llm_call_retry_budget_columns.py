"""Add retry-budget telemetry columns to ``llm_calls``.

Per the follow-up of `add-llm-retry-budget-telemetry`, persist the
same data the Prometheus signals capture so post-hoc analysis can
query it per-row without scraping the metrics endpoint.

  * ``fallback_model_used`` — text, nullable. Populated only when
    the successful response came from a model other than the
    request's primary.
  * ``retry_exhausted`` — boolean, NOT NULL, server default false.
    Set true on the last attempt of a request that exhausted the
    entire fallback chain without success.
  * ``total_latency_ms`` — integer, nullable. Wall-clock from the
    first attempt issued to the last attempt returned.

Backfill-safe: all existing rows get NULL / false defaults; no
historical row rewrites.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str = "0013"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_calls",
        sa.Column("fallback_model_used", sa.Text(), nullable=True),
    )
    op.add_column(
        "llm_calls",
        sa.Column(
            "retry_exhausted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "llm_calls",
        sa.Column("total_latency_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_calls", "total_latency_ms")
    op.drop_column("llm_calls", "retry_exhausted")
    op.drop_column("llm_calls", "fallback_model_used")
