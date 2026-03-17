"""Unit tests for app/grpc/service.py.

Covers the pure/deterministic methods without requiring a live gRPC server,
Redis, or database.  Integration-level streaming paths are exercised via the
no-Redis polling helper using a mocked async repository.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.protos import processing_pb2 as _processing_pb2

# Cast to Any to satisfy mypy — generated protobuf code has no stubs.
pb2: Any = _processing_pb2

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> Any:
    """Return a ProcessingService instance with stubbed cfg/db."""
    from app.grpc.service import ProcessingService

    cfg = MagicMock()
    cfg.runtime.request_timeout_sec = 30
    db = MagicMock()

    # Stub out repository construction so no real DB is needed.
    mp = pytest.MonkeyPatch()
    mp.setattr(
        "app.grpc.service.SqliteRequestRepositoryAdapter",
        lambda db: MagicMock(),
    )
    mp.setattr(
        "app.grpc.service.SqliteSummaryRepositoryAdapter",
        lambda db: MagicMock(),
    )
    svc = ProcessingService(cfg, db)
    mp.undo()
    return svc


# ---------------------------------------------------------------------------
# _map_status_stage
# ---------------------------------------------------------------------------


class TestMapStatusStage:
    def setup_method(self) -> None:
        self.svc = _make_service()

    def test_pending_maps_correctly(self) -> None:
        status, stage = self.svc._map_status_stage("PENDING", "QUEUED")
        assert status == pb2.ProcessingStatus.ProcessingStatus_PENDING
        assert stage == pb2.ProcessingStage.ProcessingStage_QUEUED

    def test_processing_maps_correctly(self) -> None:
        status, stage = self.svc._map_status_stage("PROCESSING", "EXTRACTION")
        assert status == pb2.ProcessingStatus.ProcessingStatus_PROCESSING
        assert stage == pb2.ProcessingStage.ProcessingStage_EXTRACTION

    def test_completed_maps_correctly(self) -> None:
        status, stage = self.svc._map_status_stage("COMPLETED", "DONE")
        assert status == pb2.ProcessingStatus.ProcessingStatus_COMPLETED
        assert stage == pb2.ProcessingStage.ProcessingStage_DONE

    def test_failed_maps_correctly(self) -> None:
        status, stage = self.svc._map_status_stage("FAILED", None)
        assert status == pb2.ProcessingStatus.ProcessingStatus_FAILED
        assert stage == pb2.ProcessingStage.ProcessingStage_UNSPECIFIED

    def test_unknown_status_falls_back_to_unspecified(self) -> None:
        status, stage = self.svc._map_status_stage("BOGUS", "BOGUS")
        assert status == pb2.ProcessingStatus.ProcessingStatus_UNSPECIFIED
        assert stage == pb2.ProcessingStage.ProcessingStage_UNSPECIFIED

    def test_none_inputs_return_unspecified(self) -> None:
        status, stage = self.svc._map_status_stage(None, None)
        assert status == pb2.ProcessingStatus.ProcessingStatus_UNSPECIFIED
        assert stage == pb2.ProcessingStage.ProcessingStage_UNSPECIFIED


# ---------------------------------------------------------------------------
# _context_active
# ---------------------------------------------------------------------------


class TestContextActive:
    def setup_method(self) -> None:
        self.svc = _make_service()

    def test_returns_true_when_context_is_active(self) -> None:
        ctx = MagicMock()
        ctx.cancelled.return_value = False
        ctx.is_active.return_value = True
        assert self.svc._context_active(ctx) is True

    def test_returns_false_when_cancelled(self) -> None:
        ctx = MagicMock()
        ctx.cancelled.return_value = True
        assert self.svc._context_active(ctx) is False

    def test_returns_false_when_not_active(self) -> None:
        ctx = MagicMock()
        ctx.cancelled.return_value = False
        ctx.is_active.return_value = False
        assert self.svc._context_active(ctx) is False

    def test_falls_back_to_true_when_no_is_active(self) -> None:
        ctx = MagicMock(spec=[])  # no attributes at all
        assert self.svc._context_active(ctx) is True


# ---------------------------------------------------------------------------
# _max_stream_seconds
# ---------------------------------------------------------------------------


class TestMaxStreamSeconds:
    def test_doubles_request_timeout(self) -> None:
        svc = _make_service()
        svc.cfg.runtime.request_timeout_sec = 45
        assert svc._max_stream_seconds() == 90

    def test_minimum_is_60(self) -> None:
        svc = _make_service()
        svc.cfg.runtime.request_timeout_sec = 10
        assert svc._max_stream_seconds() == 60


# ---------------------------------------------------------------------------
# _stream_updates_without_redis  (async, mocked repo)
# ---------------------------------------------------------------------------


class TestStreamUpdatesWithoutRedis:
    """Test the fallback DB-polling streaming path."""

    def _make_svc_with_repo(self, get_by_id_side_effect: Any) -> Any:
        svc = _make_service()
        svc.request_repo = AsyncMock()
        svc.request_repo.async_get_request_by_id.side_effect = get_by_id_side_effect
        svc.summary_repo = AsyncMock()
        svc.summary_repo.async_get_summary_by_request.return_value = {"id": 99}
        return svc

    @pytest.mark.asyncio
    async def test_yields_failed_update_when_request_not_found(self) -> None:
        svc = self._make_svc_with_repo([None])
        ctx = MagicMock()
        ctx.cancelled.return_value = False
        ctx.is_active.return_value = True

        updates = []
        async for upd in svc._stream_updates_without_redis(1, ctx):
            updates.append(upd)

        assert len(updates) == 1
        assert updates[0].status == pb2.ProcessingStatus.ProcessingStatus_FAILED
        assert updates[0].error == "not_found"

    @pytest.mark.asyncio
    async def test_yields_completed_and_attaches_summary_id(self) -> None:
        svc = self._make_svc_with_repo(
            [
                {"status": "pending"},
                {"status": "success"},
            ]
        )
        ctx = MagicMock()
        ctx.cancelled.return_value = False
        ctx.is_active.return_value = True

        updates = []
        async for upd in svc._stream_updates_without_redis(1, ctx):
            updates.append(upd)

        statuses = [u.status for u in updates]
        assert pb2.ProcessingStatus.ProcessingStatus_PENDING in statuses
        assert pb2.ProcessingStatus.ProcessingStatus_COMPLETED in statuses

        completed = next(
            u for u in updates if u.status == pb2.ProcessingStatus.ProcessingStatus_COMPLETED
        )
        assert completed.summary_id == 99

    @pytest.mark.asyncio
    async def test_yields_failed_on_error_status(self) -> None:
        svc = self._make_svc_with_repo([{"status": "error"}])
        ctx = MagicMock()
        ctx.cancelled.return_value = False
        ctx.is_active.return_value = True

        updates = []
        async for upd in svc._stream_updates_without_redis(1, ctx):
            updates.append(upd)

        assert any(u.status == pb2.ProcessingStatus.ProcessingStatus_FAILED for u in updates)

    @pytest.mark.asyncio
    async def test_stops_when_context_cancelled(self) -> None:
        call_count = 0

        async def _get_by_id(request_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {"status": "pending"}

        svc = _make_service()
        svc.request_repo = AsyncMock()
        svc.request_repo.async_get_request_by_id.side_effect = _get_by_id

        ctx = MagicMock()
        # Report cancelled on the second is_active check
        is_active_calls = [True, False]
        ctx.cancelled.return_value = False
        ctx.is_active.side_effect = is_active_calls + [False] * 100

        updates = []
        async for upd in svc._stream_updates_without_redis(1, ctx):
            updates.append(upd)
            if len(updates) >= 5:  # safety valve
                break

        # The loop must have exited — we just verify no infinite loop occurred.
        assert call_count < 10

    @pytest.mark.asyncio
    async def test_yields_timeout_update_when_max_seconds_exceeded(self) -> None:
        import time

        svc = _make_service()
        svc.request_repo = AsyncMock()
        svc.request_repo.async_get_request_by_id.return_value = {"status": "pending"}
        svc.cfg.runtime.request_timeout_sec = 1  # 2s max

        ctx = MagicMock()
        ctx.cancelled.return_value = False
        ctx.is_active.return_value = True

        # Monkey-patch time.monotonic to fast-forward past the deadline.
        original_monotonic = time.monotonic
        start = original_monotonic()

        call_count = 0

        def fake_monotonic() -> float:
            nonlocal call_count
            call_count += 1
            # First call (guard check) returns start; subsequent calls return start + 200.
            if call_count <= 1:
                return start
            return start + 200

        import unittest.mock

        with unittest.mock.patch("time.monotonic", side_effect=fake_monotonic):
            updates = []
            async for upd in svc._stream_updates_without_redis(1, ctx):
                updates.append(upd)

        assert any(u.error == "timeout" for u in updates)
