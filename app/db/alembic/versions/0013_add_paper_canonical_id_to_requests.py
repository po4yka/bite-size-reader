"""Add ``paper_canonical_id`` to requests for academic-paper dedupe.

Lets two different URLs pointing at the same academic paper
(``arxiv.org/abs/X`` and ``arxiv.org/pdf/X.pdf``, v1 and v2, etc.)
dedupe to one ``requests`` row via a canonical id of the form
``<host>:<paper_id>`` — e.g. ``arxiv:2301.00001``, ``ssrn:6531478``,
``doi:10.xxxx/...``.

The column is nullable for every non-academic request. Postgres treats
NULLs as distinct under a UNIQUE constraint, so multiple NULL rows
coexist without a partial index. The unique constraint enforces
single-paper dedupe for non-NULL values, mirroring the existing
``dedupe_hash`` column.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str = "0012"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

_COLUMN = "paper_canonical_id"
_CONSTRAINT = "uq_requests_paper_canonical_id"


def upgrade() -> None:
    op.add_column(
        "requests",
        sa.Column(_COLUMN, sa.Text(), nullable=True),
    )
    op.create_unique_constraint(_CONSTRAINT, "requests", [_COLUMN])


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "requests", type_="unique")
    op.drop_column("requests", _COLUMN)
