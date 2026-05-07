"""widen summaries.version from INTEGER to BIGINT.

Legacy `BaseModel.save()` overrides `Summary.version` with the same
millisecond-resolution timestamp it uses for `server_version` (see
`app/cli/_legacy_peewee_models/_base.py:42-43`). Those values are
~1.7e12 — they fit SQLite's flexible INTEGER but overflow Postgres
INTEGER (max 2.1e9), so the SQLite -> Postgres migrator
(`app.cli.migrate_sqlite_to_postgres`) fails with
`asyncpg.DataError: value out of int32 range` on the very first
Summary insert.

Widening to BIGINT matches `Summary.server_version` (also BIGINT) and
lets every legacy row migrate unchanged. Production-relevant: the
live Pi `summaries` table has the same value pattern, so this
revision is a prerequisite for C2 (Pi cutover).

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.alter_column(
        "summaries",
        "version",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
        existing_server_default=None,
    )


def downgrade() -> None:
    op.alter_column(
        "summaries",
        "version",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
        existing_server_default=None,
    )
