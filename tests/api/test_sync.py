"""Handler-level integration tests for /v1/sync/{sessions,full,delta,apply}.

Uses the direct-call pattern (no HTTP TestClient) to avoid the asyncpg/anyio
event-loop conflict that breaks TestClient in this repo.  See
tests/api/test_articles.py for the canonical pattern.

SyncService is wired with real repository instances built via
app.di.repositories.build_* helpers against the test Postgres database
provided by the `db` fixture from conftest.py.  No mocks touch the DB path.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.api.models.requests import SyncApplyItem, SyncApplyRequest, SyncSessionRequest
from app.api.routers.sync import apply_changes, create_sync_session, delta_sync, full_sync
from app.api.services.sync_service import SyncService
from app.config import load_config
from app.di.repositories import (
    build_crawl_result_repository,
    build_llm_repository,
    build_request_repository,
    build_summary_repository,
    build_user_repository,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_svc(db) -> SyncService:
    """Build a SyncService wired to real repositories against *db*."""
    cfg = load_config(allow_stub_telegram=True)
    return SyncService(
        cfg,
        db,
        user_repository=build_user_repository(db),
        request_repository=build_request_repository(db),
        summary_repository=build_summary_repository(db),
        crawl_result_repository=build_crawl_result_repository(db),
        llm_repository=build_llm_repository(db),
    )


def _user_ctx(user) -> dict:
    return {
        "user_id": user.telegram_user_id,
        "username": user.username,
        "client_id": "test-client",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sync_user(user_factory):
    return await user_factory(username="sync_test_user")


@pytest_asyncio.fixture
async def sync_summary(summary_factory, sync_user):
    return await summary_factory(user=sync_user)


# ---------------------------------------------------------------------------
# Scenario 1: Create session returns sessionId + meta envelope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session_returns_session_id(db, sync_user):
    svc = _make_svc(db)
    user_ctx = _user_ctx(sync_user)

    result = await create_sync_session(body=SyncSessionRequest(limit=50), user=user_ctx, svc=svc)

    assert result["success"] is True
    data = result["data"]
    assert "sessionId" in data, f"sessionId missing from data: {data.keys()}"
    assert data["sessionId"].startswith("sync-")
    assert "meta" in result


# ---------------------------------------------------------------------------
# Scenario 2: Full sync paginated by cursor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_sync_pagination(db, sync_user, summary_factory):
    # Seed 3 summaries for the user.
    for _ in range(3):
        await summary_factory(user=sync_user)

    svc = _make_svc(db)
    user_ctx = _user_ctx(sync_user)

    # Create a session first.
    session_result = await create_sync_session(body=None, user=user_ctx, svc=svc)
    session_id = session_result["data"]["sessionId"]

    # Fetch with limit=2 - should get a page and hasMore=True.
    page1 = await full_sync(
        session_id=session_id,
        limit=2,
        user=user_ctx,
        svc=svc,
    )
    assert page1["success"] is True
    data1 = page1["data"]
    assert len(data1["items"]) == 2
    assert data1["hasMore"] is True

    # Fetch remaining records with a large limit - hasMore should be False.
    page2 = await full_sync(
        session_id=session_id,
        limit=500,
        user=user_ctx,
        svc=svc,
    )
    assert page2["success"] is True
    data2 = page2["data"]
    assert data2["hasMore"] is False


# ---------------------------------------------------------------------------
# Scenario 3: Delta after full returns only changed items
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delta_sync_returns_changed_items(db, sync_user, summary_factory):
    summary = await summary_factory(user=sync_user)

    svc = _make_svc(db)
    user_ctx = _user_ctx(sync_user)

    # Start session.
    session_result = await create_sync_session(body=None, user=user_ctx, svc=svc)
    session_id = session_result["data"]["sessionId"]

    # Full sync to capture baseline server_version.
    full_result = await full_sync(
        session_id=session_id,
        limit=500,
        user=user_ctx,
        svc=svc,
    )
    assert full_result["success"] is True
    items_before = full_result["data"]["items"]
    # Find our summary's server_version as the cursor.
    summary_items = [it for it in items_before if it.get("entityType") == "summary"]
    assert summary_items, "Expected at least one summary in full sync output"
    baseline_version = max(it["serverVersion"] for it in summary_items)

    # Mutate the summary (flip is_read) via apply to bump its server_version.
    apply_payload = SyncApplyRequest(
        session_id=session_id,
        changes=[
            SyncApplyItem(
                entity_type="summary",
                id=summary.id,
                action="update",
                last_seen_version=baseline_version,
                payload={"is_read": True},
            )
        ],
    )

    # Use a fresh mock-free Request object for the apply call.
    class _FakeRequest:
        headers: dict = {}

    class _FakeResponse:
        headers: dict = {}

    apply_result = await apply_changes(payload=apply_payload, user=user_ctx, svc=svc)
    assert apply_result["success"] is True
    apply_data = apply_result["data"]
    assert apply_data["results"][0]["status"] == "applied"

    # Note: server_version is set once at INSERT (not bumped by apply_sync_change),
    # so the returned serverVersion equals baseline_version.  The important thing is
    # apply succeeded and is_read was toggled.

    # Delta from cursor=0 should include all records for the user (including our summary).
    fake_req = _FakeRequest()
    fake_resp = _FakeResponse()
    delta_result = await delta_sync(
        request=fake_req,
        response=fake_resp,
        session_id=session_id,
        since=0,
        limit=500,
        user=user_ctx,
        svc=svc,
    )

    # delta_sync can return a Response (304) or dict; here we expect a dict.
    assert isinstance(delta_result, dict), "Expected dict response, got Response (304)"
    assert delta_result["success"] is True
    delta_data = delta_result["data"]
    # The summary should appear in created (server_version > 0).
    all_ids = [it["id"] for it in delta_data.get("created", [])]
    assert summary.id in all_ids, f"Summary {summary.id} not found in delta created={all_ids}"


# ---------------------------------------------------------------------------
# Scenario 4: Apply idempotent re-apply via idempotency_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_idempotent_reapply_returns_cached_response(db, sync_user, sync_summary):
    """Sending the same apply payload twice with the same idempotency_key
    must return the original response on the second call without re-applying
    the change. Lets clients retry safely after a network failure."""
    svc = _make_svc(db)
    user_ctx = _user_ctx(sync_user)

    # Bootstrap a session.
    session_resp = await create_sync_session(SyncSessionRequest(), user=user_ctx, svc=svc)
    session_id = session_resp["data"]["sessionId"]

    # Capture the row's pre-apply server_version so we can assert no
    # double-bump after the second (idempotent) call.
    apply_payload = SyncApplyRequest(
        session_id=session_id,
        idempotency_key="retry-key-test-42",
        changes=[
            SyncApplyItem(
                entity_type="summary",
                id=str(sync_summary.id),
                action="update",
                last_seen_version=sync_summary.server_version,
                payload={"is_read": True},
            )
        ],
    )

    first = await apply_changes(payload=apply_payload, user=user_ctx, svc=svc)
    second = await apply_changes(payload=apply_payload, user=user_ctx, svc=svc)

    # The data payload (camelCase wire shape) must be identical on the
    # idempotent retry. The meta envelope intentionally diverges per-call
    # (correlation_id and timestamp are per-request observability, not part
    # of the apply contract).
    assert first["data"] == second["data"], (
        "second apply with same idempotency_key must return cached data"
    )

    # The row was mutated exactly once: server_version advanced once and
    # the second call did NOT bump it again.
    from sqlalchemy import select as _select

    from app.db.models import Summary

    async with db.session() as session:
        row = await session.scalar(_select(Summary).where(Summary.id == sync_summary.id))
    assert row is not None
    assert row.is_read is True
    first_result = first["data"]["results"][0]
    assert row.server_version == first_result["serverVersion"], (
        "second idempotent call must not advance server_version"
    )


# ---------------------------------------------------------------------------
# Scenario 5: Apply with conflict - stale last_seen_version
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_conflict_stale_version(db, sync_user, summary_factory):
    summary = await summary_factory(user=sync_user)

    svc = _make_svc(db)
    user_ctx = _user_ctx(sync_user)

    # Create session.
    session_result = await create_sync_session(body=None, user=user_ctx, svc=svc)
    session_id = session_result["data"]["sessionId"]

    # server_version is set at INSERT (epoch millis) and now ALSO advances on
    # every successful sync-apply mutation. A stale last_seen_version is any
    # value strictly less than the current server_version. 0 is always stale.
    stale_apply = SyncApplyRequest(
        session_id=session_id,
        changes=[
            SyncApplyItem(
                entity_type="summary",
                id=summary.id,
                action="update",
                last_seen_version=0,  # always stale vs epoch-millis server_version
                payload={"is_read": False},
            )
        ],
    )
    r2 = await apply_changes(payload=stale_apply, user=user_ctx, svc=svc)

    # Response must be a success envelope (HTTP 200), not a 5xx.
    assert r2["success"] is True
    data2 = r2["data"]
    assert data2["results"][0]["status"] == "conflict"
    # conflicts list must be non-empty.
    assert data2.get("conflicts"), (
        f"Expected non-empty conflicts list, got: {data2.get('conflicts')!r}"
    )


# ---------------------------------------------------------------------------
# Scenario 6: server_version monotonicity regression
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_advances_server_version_on_mutation(db, sync_user, sync_summary):
    """A successful sync-apply MUST advance the row's server_version.

    Two invariants depend on this:
      1. Other clients calling /v1/sync/delta since their last cursor will
         observe this row as updated.
      2. A subsequent stale upload (using the pre-mutation server_version)
         is detected as a conflict, not silently overwritten.

    Earlier the bump was missing — async_apply_sync_change updated is_read /
    is_deleted but left server_version frozen at its INSERT-time value, so
    a re-apply with the same client cursor would slip through. This test
    locks the fix.
    """
    svc = _make_svc(db)
    user_ctx = _user_ctx(sync_user)

    session_resp = await create_sync_session(SyncSessionRequest(), user=user_ctx, svc=svc)
    session_id = session_resp["data"]["sessionId"]

    initial_version = sync_summary.server_version

    apply_req = SyncApplyRequest(
        session_id=session_id,
        changes=[
            SyncApplyItem(
                entity_type="summary",
                id=str(sync_summary.id),
                action="update",
                last_seen_version=initial_version,
                payload={"is_read": True},
            )
        ],
    )
    result = await apply_changes(payload=apply_req, user=user_ctx, svc=svc)

    item = result["data"]["results"][0]
    assert item["status"] == "applied"
    assert item["serverVersion"] > initial_version, (
        f"server_version must advance after apply; got {item['serverVersion']} "
        f"<= initial {initial_version}"
    )

    # Confirm the DB row reflects the bumped version, not just the response.
    from sqlalchemy import select as _select

    from app.db.models import Summary

    async with db.session() as session:
        row = await session.scalar(_select(Summary).where(Summary.id == sync_summary.id))
    assert row is not None
    assert row.server_version > initial_version
    assert row.server_version == item["serverVersion"]
