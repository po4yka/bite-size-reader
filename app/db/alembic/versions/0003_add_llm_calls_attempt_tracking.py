"""add llm_calls attempt_index and attempt_trigger, and requests initial_attempt_trigger.

Adds two observability columns to ``llm_calls`` so every row attributes
itself to a known retry pathway:

* ``attempt_index`` (INTEGER NOT NULL DEFAULT 1) — 1-based index within a
  request's attempt sequence.  The first OpenRouter call for a request gets
  1; subsequent calls for the same ``request_id`` increment.

* ``attempt_trigger`` (llm_attempt_trigger enum NOT NULL DEFAULT 'initial') —
  identifies the pathway that created the row.  Values: initial, user_retry,
  auto_backfill (reserved), repair_loop, stream_fallback_retry (reserved).

Also adds ``requests.initial_attempt_trigger`` (nullable TEXT) so that retry
flows (``RequestService.retry_failed_request``) can mark a cloned request so
its first LLM call inherits the correct trigger without modifying every call
site.

A composite index ``ix_llm_calls_request_id_attempt_index`` on
``(request_id, attempt_index)`` is created for cheap retrieval of "all
attempts for a request, ordered".

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

# Postgres enum type name — must match the SQLAlchemy Enum(name=...) in the model.
_ENUM_NAME = "llm_attempt_trigger"
_ENUM_VALUES = ("initial", "user_retry", "auto_backfill", "repair_loop", "stream_fallback_retry")


def upgrade() -> None:
    # 1. Create the Postgres enum type.
    llm_attempt_trigger = postgresql.ENUM(
        *_ENUM_VALUES,
        name=_ENUM_NAME,
        create_type=True,
    )
    llm_attempt_trigger.create(op.get_bind(), checkfirst=True)

    # 2. Add columns to llm_calls.
    op.add_column(
        "llm_calls",
        sa.Column(
            "attempt_index",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="1-based index within a request's attempt sequence.",
        ),
    )
    op.add_column(
        "llm_calls",
        sa.Column(
            "attempt_trigger",
            sa.Enum(
                *_ENUM_VALUES,
                name=_ENUM_NAME,
                native_enum=True,
                create_constraint=False,  # type already created above
            ),
            nullable=False,
            server_default="initial",
            comment="Pathway that created this LLM call row. See LLMAttemptTrigger.",
        ),
    )

    # 3. Composite index for efficient "all attempts for a request" queries.
    op.create_index(
        "ix_llm_calls_request_id_attempt_index",
        "llm_calls",
        ["request_id", "attempt_index"],
    )

    # 4. Add nullable hint column to requests.
    op.add_column(
        "requests",
        sa.Column(
            "initial_attempt_trigger",
            sa.Text(),
            nullable=True,
            comment=(
                "When set, the first LLM call for this request inherits this trigger "
                "value. Used by retry flows to propagate user_retry without modifying "
                "every LLM call site."
            ),
        ),
    )


def downgrade() -> None:
    # 4. Drop the hint column from requests.
    op.drop_column("requests", "initial_attempt_trigger")

    # 3. Drop the composite index.
    op.drop_index("ix_llm_calls_request_id_attempt_index", table_name="llm_calls")

    # 2. Drop columns from llm_calls.
    op.drop_column("llm_calls", "attempt_trigger")
    op.drop_column("llm_calls", "attempt_index")

    # 1. Drop the Postgres enum type.
    llm_attempt_trigger = postgresql.ENUM(
        *_ENUM_VALUES,
        name=_ENUM_NAME,
        create_type=False,
    )
    llm_attempt_trigger.drop(op.get_bind(), checkfirst=True)
