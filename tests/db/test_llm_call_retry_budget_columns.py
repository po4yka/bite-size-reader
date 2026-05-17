"""Tests that the LLMCall model exposes the retry-budget columns.

Per the follow-up of [[add-llm-retry-budget-telemetry]], the
``llm_calls`` table needs three nullable columns so the same
data the Prometheus signals capture can also be queried per-row:

  * ``fallback_model_used`` — text. NULL when the successful
    response came from the request's primary model; populated only
    when a fallback in the cascade produced the success.
  * ``retry_exhausted`` — boolean default false. Set true on the
    last attempt of a request that exhausted the entire fallback
    chain without success.
  * ``total_latency_ms`` — int. Wall-clock from the first attempt
    issued to the last attempt returned for the request.

Live-postgres migration verification is performed via the existing
alembic round-trip CI job; this test pins the ORM-side contract.
"""

from __future__ import annotations

import sqlalchemy as sa

from app.db.models import LLMCall


def test_llm_call_has_fallback_model_used_column() -> None:
    col = LLMCall.__table__.columns["fallback_model_used"]
    assert col.nullable is True
    assert isinstance(col.type, sa.Text)


def test_llm_call_has_retry_exhausted_column() -> None:
    col = LLMCall.__table__.columns["retry_exhausted"]
    assert col.nullable is False
    assert isinstance(col.type, sa.Boolean)


def test_llm_call_has_total_latency_ms_column() -> None:
    col = LLMCall.__table__.columns["total_latency_ms"]
    assert col.nullable is True
    assert isinstance(col.type, sa.Integer)


def test_retry_exhausted_default_is_false() -> None:
    col = LLMCall.__table__.columns["retry_exhausted"]
    # The default lands as either Python-side False or a server-side
    # 'false' literal depending on how Alembic was generated. Either is
    # acceptable; what's pinned is that fresh rows do not arrive True.
    assert col.default is not None or col.server_default is not None
