"""Smoke tests for `tests/db_helpers_async.py` and the new async fixtures.

These tests exercise the T3 Phase 1 foundation (the `database` and `session`
fixtures in `tests/conftest.py` plus the async helpers in
`tests/db_helpers_async.py`) end-to-end against a live Postgres. They skip
cleanly if `TEST_DATABASE_URL` is not set.
"""

from __future__ import annotations

import pytest

from tests import db_helpers_async as dbh

pytestmark = pytest.mark.asyncio


async def test_create_request_assigns_id_and_persists(session) -> None:
    request_id = await dbh.create_request(
        session,
        type_="url",
        status="received",
        correlation_id="smoke-corr-1",
        input_url="https://example.com/a",
        normalized_url="https://example.com/a",
        dedupe_hash="smoke-hash-1",
    )
    assert request_id > 0

    fetched = await dbh.get_request_by_dedupe_hash(session, "smoke-hash-1")
    assert fetched is not None
    assert fetched["id"] == request_id
    assert fetched["status"] == "received"
    assert fetched["correlation_id"] == "smoke-corr-1"


async def test_create_request_dedupe_hash_upserts_existing_row(session) -> None:
    first = await dbh.create_request(
        session,
        type_="url",
        status="received",
        input_url="https://example.com/b",
        normalized_url="https://example.com/b",
        dedupe_hash="smoke-hash-2",
    )
    second = await dbh.create_request(
        session,
        type_="url",
        status="completed",
        input_url="https://example.com/b",
        normalized_url="https://example.com/b",
        dedupe_hash="smoke-hash-2",
        correlation_id="smoke-corr-2",
    )
    assert first == second  # same row, same id

    fetched = await dbh.get_request_by_dedupe_hash(session, "smoke-hash-2")
    assert fetched is not None
    assert fetched["status"] == "completed"
    assert fetched["correlation_id"] == "smoke-corr-2"


async def test_summary_lifecycle_and_read_status(session) -> None:
    request_id = await dbh.create_request(
        session,
        type_="url",
        status="completed",
        input_url="https://example.com/c",
        normalized_url="https://example.com/c",
        dedupe_hash="smoke-hash-3",
    )
    summary_id = await dbh.insert_summary(
        session,
        request_id=request_id,
        lang="en",
        json_payload={"summary_250": "smoke summary"},
    )
    assert summary_id > 0

    assert await dbh.get_read_status(session, request_id) is False
    await dbh.mark_summary_as_read(session, request_id)
    assert await dbh.get_read_status(session, request_id) is True

    fetched_summary = await dbh.get_summary_by_request(session, request_id)
    assert fetched_summary is not None
    assert fetched_summary["lang"] == "en"


async def test_truncate_cleanup_isolates_rows_between_tests(session) -> None:
    """Verify the conftest `session` fixture truncates between tests."""
    fetched = await dbh.get_request_by_dedupe_hash(session, "smoke-hash-1")
    assert fetched is None  # the row from the first test must be gone


async def test_user_chat_upsert_round_trip(session) -> None:
    await dbh.upsert_user(
        session, telegram_user_id=8001, username="smoke", is_owner=True
    )
    await dbh.upsert_user(
        session, telegram_user_id=8001, username="smoke-renamed", is_owner=False
    )
    await dbh.upsert_chat(session, chat_id=9001, type_="private", title="Smoke Chat")

    from sqlalchemy import select

    from app.db.models import Chat, User

    user = await session.scalar(select(User).where(User.telegram_user_id == 8001))
    assert user is not None
    assert user.username == "smoke-renamed"
    assert user.is_owner is False

    chat = await session.scalar(select(Chat).where(Chat.chat_id == 9001))
    assert chat is not None
    assert chat.type == "private"
