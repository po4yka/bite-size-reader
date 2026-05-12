"""Add supporting indexes for the vector-index reconciler.

The reconciler (``app/tasks/reconcile_vector_index.py``) issues a query that:

  1. Joins ``summaries`` → ``requests`` → ``summary_embeddings`` (LEFT OUTER).
  2. Filters on ``summaries.is_deleted = false`` and
     ``(summary_embeddings.id IS NULL
       OR summary_embeddings.last_indexed_at IS NULL
       OR summary_embeddings.last_indexed_at < summaries.updated_at)``.
  3. Orders by ``summaries.updated_at ASC`` with a LIMIT.

Without dedicated indexes Postgres falls back to sequential scans on both
tables for every 30-minute reconciler tick.

Indexes added
-------------
1. ``ix_summaries_updated_at_where_not_deleted``
   Partial index on ``summaries (updated_at)`` filtered to
   ``WHERE is_deleted = false``.  Matches the reconciler's filter exactly,
   keeps the index small, and accelerates the ORDER BY + LIMIT scan.

2. ``ix_summary_embeddings_summary_id_last_indexed``
   Covering composite index on ``summary_embeddings (summary_id, last_indexed_at)``.
   The single-column ``ix_summary_embeddings_last_indexed_at`` (added in 0007)
   cannot satisfy the ``summary_id`` join probe efficiently.  This index
   replaces it functionally for the reconciler's access pattern while keeping
   the old index in place for other callers.

Both indexes are built CONCURRENTLY (no table lock) inside autocommit blocks.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str = "0009"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

_IDX_SUMMARIES = "ix_summaries_updated_at_where_not_deleted"
_IDX_EMBEDDINGS = "ix_summary_embeddings_summary_id_last_indexed"


def upgrade() -> None:
    # Both CREATE INDEX CONCURRENTLY statements must run outside a
    # transaction block (Postgres requirement).  Alembic's
    # ``autocommit_block()`` context manager temporarily disables the
    # surrounding transaction for the duration of the block.

    with op.get_context().autocommit_block():
        # 1. Partial index on summaries.updated_at for non-deleted rows.
        op.execute(
            sa.text(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {_IDX_SUMMARIES}
                    ON summaries (updated_at)
                    WHERE is_deleted = false
                """
            )
        )

        # 2. Covering composite index on summary_embeddings for the reconciler
        #    join probe: (summary_id, last_indexed_at).
        op.execute(
            sa.text(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {_IDX_EMBEDDINGS}
                    ON summary_embeddings (summary_id, last_indexed_at)
                """
            )
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {_IDX_EMBEDDINGS}")
        )

        op.execute(
            sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {_IDX_SUMMARIES}")
        )
