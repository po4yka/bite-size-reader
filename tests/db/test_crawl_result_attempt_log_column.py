"""Tests that CrawlResult exposes the scraper-chain attempt log columns.

Per the follow-up of [[add-scraper-chain-failure-metrics]]:

  * ``attempt_log`` — JSON, nullable. Holds the serialized list of
    :class:`ScraperAttemptEntry` rows (one per provider call) so
    multi-provider failure paths are auditable from the row itself.
  * ``winning_provider`` — text, nullable. Tags each row with the
    provider that produced the successful response; lets operators
    pick which providers to drop from the chain.

Live-postgres migration verification belongs in the alembic
round-trip CI job; this test pins the ORM-side contract.
"""

from __future__ import annotations

import sqlalchemy as sa

from app.db.models import CrawlResult


def test_attempt_log_column_is_json_nullable() -> None:
    col = CrawlResult.__table__.columns["attempt_log"]
    assert col.nullable is True
    # JSON column can be either sa.JSON or a JSONB variant depending
    # on the project's _json_column helper.
    type_name = type(col.type).__name__.upper()
    assert "JSON" in type_name


def test_winning_provider_column_is_text_nullable() -> None:
    col = CrawlResult.__table__.columns["winning_provider"]
    assert col.nullable is True
    assert isinstance(col.type, sa.Text)
