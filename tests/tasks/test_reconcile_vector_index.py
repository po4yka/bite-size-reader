"""Tests for app.tasks.reconcile_vector_index."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _stub_taskiq(monkeypatch):
    for mod_name in (
        "taskiq",
        "taskiq.abc",
        "taskiq.abc.schedule_source",
        "taskiq.scheduler",
        "taskiq.scheduler.scheduled_task",
        "taskiq.message",
        "taskiq_redis",
    ):
        if mod_name not in sys.modules:
            monkeypatch.setitem(sys.modules, mod_name, types.ModuleType(mod_name))

    taskiq_mod = sys.modules["taskiq"]
    taskiq_mod.AsyncBroker = object
    taskiq_mod.TaskiqDepends = lambda fn, **_kw: None
    taskiq_mod.TaskiqMiddleware = object
    taskiq_mod.InMemoryBroker = MagicMock
    taskiq_mod.TaskiqScheduler = MagicMock

    msg_mod = sys.modules["taskiq.message"]
    msg_mod.TaskiqMessage = object

    sched_task_mod = sys.modules["taskiq.scheduler.scheduled_task"]
    sched_task_mod.ScheduledTask = MagicMock

    source_mod = sys.modules["taskiq.abc.schedule_source"]
    source_mod.ScheduleSource = object

    tkr_mod = sys.modules["taskiq_redis"]
    tkr_mod.RedisStreamBroker = MagicMock
    tkr_mod.RedisAsyncResultBackend = MagicMock


def _evict_app_tasks() -> None:
    for mod in list(sys.modules):
        if mod.startswith("app.tasks"):
            sys.modules.pop(mod, None)


def _build_cfg(*, enabled: bool = True, batch_size: int = 100) -> SimpleNamespace:
    return SimpleNamespace(
        vector_reconcile=SimpleNamespace(
            enabled=enabled,
            batch_size=batch_size,
            cron="*/30 * * * *",
        ),
        embedding=SimpleNamespace(max_token_length=512),
    )


@pytest.mark.asyncio
async def test_reconcile_short_circuits_when_disabled(monkeypatch):
    _stub_taskiq(monkeypatch)
    monkeypatch.setenv("TASKIQ_BROKER", "memory")
    _evict_app_tasks()

    from app.tasks.reconcile_vector_index import _reconcile_body

    fetch_spy = AsyncMock()
    monkeypatch.setattr(
        "app.tasks.reconcile_vector_index._fetch_stale_summaries",
        fetch_spy,
    )

    summary = await _reconcile_body(_build_cfg(enabled=False), MagicMock())

    assert summary.scanned == 0
    assert summary.requeued == 0
    fetch_spy.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_returns_zero_when_no_stale_rows(monkeypatch):
    _stub_taskiq(monkeypatch)
    monkeypatch.setenv("TASKIQ_BROKER", "memory")
    _evict_app_tasks()

    from app.tasks.reconcile_vector_index import _reconcile_body

    monkeypatch.setattr(
        "app.tasks.reconcile_vector_index._fetch_stale_summaries",
        AsyncMock(return_value=[]),
    )

    summary = await _reconcile_body(_build_cfg(), MagicMock())

    assert summary == summary.__class__(scanned=0, requeued=0, skipped=0, failed=0)


@pytest.mark.asyncio
async def test_reconcile_requeues_stale_rows_with_force_true(monkeypatch):
    _stub_taskiq(monkeypatch)
    monkeypatch.setenv("TASKIQ_BROKER", "memory")
    _evict_app_tasks()

    from app.tasks.reconcile_vector_index import _reconcile_body

    rows = [
        {
            "summary_id": 11,
            "json_payload": {"summary_250": "a"},
            "lang_detected": "en",
        },
        {
            "summary_id": 22,
            "json_payload": {"summary_250": "b"},
            "lang_detected": "ru",
        },
        {
            "summary_id": 33,
            # Non-dict payload — should be counted as skipped, not failed.
            "json_payload": "legacy-string",
            "lang_detected": None,
        },
    ]
    monkeypatch.setattr(
        "app.tasks.reconcile_vector_index._fetch_stale_summaries",
        AsyncMock(return_value=rows),
    )

    fake_generator = SimpleNamespace(
        generate_embedding_for_summary=AsyncMock(side_effect=[True, False])
    )
    monkeypatch.setattr(
        "app.tasks.reconcile_vector_index._build_generator",
        lambda _cfg, _db: fake_generator,
    )

    summary = await _reconcile_body(_build_cfg(), MagicMock())

    assert summary.scanned == 3
    assert summary.requeued == 1  # one True
    assert summary.skipped == 2  # one False + one non-dict payload
    assert summary.failed == 0

    calls = fake_generator.generate_embedding_for_summary.await_args_list
    assert [c.kwargs["summary_id"] for c in calls] == [11, 22]
    assert all(c.kwargs["force"] is True for c in calls)
    assert calls[0].kwargs["language"] == "en"
    assert calls[1].kwargs["language"] == "ru"


@pytest.mark.asyncio
async def test_reconcile_swallows_per_summary_exceptions(monkeypatch):
    _stub_taskiq(monkeypatch)
    monkeypatch.setenv("TASKIQ_BROKER", "memory")
    _evict_app_tasks()

    from app.tasks.reconcile_vector_index import _reconcile_body

    monkeypatch.setattr(
        "app.tasks.reconcile_vector_index._fetch_stale_summaries",
        AsyncMock(
            return_value=[
                {"summary_id": 1, "json_payload": {"x": 1}, "lang_detected": None},
                {"summary_id": 2, "json_payload": {"x": 2}, "lang_detected": None},
            ]
        ),
    )

    fake_generator = SimpleNamespace(
        generate_embedding_for_summary=AsyncMock(side_effect=[RuntimeError("boom"), True])
    )
    monkeypatch.setattr(
        "app.tasks.reconcile_vector_index._build_generator",
        lambda _cfg, _db: fake_generator,
    )

    summary = await _reconcile_body(_build_cfg(), MagicMock())

    assert summary.scanned == 2
    assert summary.requeued == 1
    assert summary.failed == 1
    assert summary.skipped == 0
