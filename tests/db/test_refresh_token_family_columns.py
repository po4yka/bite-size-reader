"""Tests that RefreshToken exposes the token-family columns.

Per the follow-up of [[harden-refresh-token-rotation-revocation]]:

  * ``family_id`` — text, NOT NULL. Every refresh token belongs to a
    family; rotation issues a new token in the same family; reuse
    of a retired token revokes the whole family.
  * ``parent_token_hash`` — text, nullable. NULL for the root token
    of each family; populated with the hash of the predecessor
    after a rotation.

Live-postgres migration verification belongs in the alembic
round-trip CI job; this test pins the ORM-side contract.
"""

from __future__ import annotations

import sqlalchemy as sa

from app.db.models import RefreshToken


def test_family_id_column_is_text_not_null() -> None:
    col = RefreshToken.__table__.columns["family_id"]
    assert col.nullable is False
    assert isinstance(col.type, sa.Text)


def test_parent_token_hash_column_is_text_nullable() -> None:
    col = RefreshToken.__table__.columns["parent_token_hash"]
    assert col.nullable is True
    assert isinstance(col.type, sa.Text)
