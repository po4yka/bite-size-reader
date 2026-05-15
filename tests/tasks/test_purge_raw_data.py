"""Tests for app.tasks.purge_raw_data."""

from __future__ import annotations

import datetime as dt
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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


def _build_cfg(
    *,
    enabled=True,
    batch_size=100,
    telegram_raw_days=7,
    crawl_content_days=7,
    llm_payload_days=7,
    video_transcript_days=7,
    interaction_text_days=7,
    request_content_days=7,
):
    return SimpleNamespace(
        retention=SimpleNamespace(
            enabled=enabled,
            batch_size=batch_size,
            telegram_raw_days=telegram_raw_days,
            crawl_content_days=crawl_content_days,
            llm_payload_days=llm_payload_days,
            video_transcript_days=video_transcript_days,
            interaction_text_days=interaction_text_days,
            request_content_days=request_content_days,
        )
    )


def _make_mock_db(rowcount=3):
    """Return mock Database whose session yields rowcount on execute."""
    mock_db = MagicMock()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = rowcount
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_db.session.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_body_disabled_returns_zero_stats(monkeypatch):
    _stub_taskiq(monkeypatch)
    monkeypatch.setenv("TASKIQ_BROKER", "memory")
    _evict_app_tasks()

    from app.tasks.purge_raw_data import PurgeStats, _purge_body

    mock_db = _make_mock_db(rowcount=5)
    result = await _purge_body(_build_cfg(enabled=False), mock_db)

    assert result == PurgeStats()
    mock_db.session.assert_not_called()


@pytest.mark.asyncio
async def test_null_columns_ttl_zero_skips_db(monkeypatch):
    _stub_taskiq(monkeypatch)
    monkeypatch.setenv("TASKIQ_BROKER", "memory")
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_telegram_raw

    mock_db = _make_mock_db(rowcount=5)
    now = dt.datetime.now(dt.UTC)

    result = await _purge_telegram_raw(mock_db, now, days=0, batch=100)

    assert result == 0
    mock_db.session.assert_not_called()


@pytest.mark.asyncio
async def test_purge_telegram_raw_returns_rowcount(monkeypatch):
    _stub_taskiq(monkeypatch)
    monkeypatch.setenv("TASKIQ_BROKER", "memory")
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_telegram_raw

    mock_db = _make_mock_db(rowcount=5)
    now = dt.datetime.now(dt.UTC)

    result = await _purge_telegram_raw(mock_db, now, days=7, batch=100)

    assert result == 5
    mock_db.session.return_value.__aenter__.assert_called_once()
    session = await mock_db.session.return_value.__aenter__()
    session.execute.assert_called_once()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_purge_crawl_content_returns_rowcount(monkeypatch):
    _stub_taskiq(monkeypatch)
    monkeypatch.setenv("TASKIQ_BROKER", "memory")
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_crawl_content

    mock_db = _make_mock_db(rowcount=3)
    now = dt.datetime.now(dt.UTC)

    result = await _purge_crawl_content(mock_db, now, days=7, batch=100)

    assert result == 3
    session = await mock_db.session.return_value.__aenter__()
    session.execute.assert_called()
    session.commit.assert_called()


@pytest.mark.asyncio
async def test_purge_llm_payload_returns_rowcount(monkeypatch):
    _stub_taskiq(monkeypatch)
    monkeypatch.setenv("TASKIQ_BROKER", "memory")
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_llm_payload

    mock_db = _make_mock_db(rowcount=12)
    now = dt.datetime.now(dt.UTC)

    result = await _purge_llm_payload(mock_db, now, days=7, batch=100)

    assert result == 12
    session = await mock_db.session.return_value.__aenter__()
    session.execute.assert_called()
    session.commit.assert_called()


@pytest.mark.asyncio
async def test_purge_video_transcript_returns_rowcount(monkeypatch):
    _stub_taskiq(monkeypatch)
    monkeypatch.setenv("TASKIQ_BROKER", "memory")
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_video_transcript

    mock_db = _make_mock_db(rowcount=2)
    now = dt.datetime.now(dt.UTC)

    result = await _purge_video_transcript(mock_db, now, days=7, batch=100)

    assert result == 2
    session = await mock_db.session.return_value.__aenter__()
    session.execute.assert_called()
    session.commit.assert_called()


@pytest.mark.asyncio
async def test_purge_interaction_text_returns_rowcount(monkeypatch):
    _stub_taskiq(monkeypatch)
    monkeypatch.setenv("TASKIQ_BROKER", "memory")
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_interaction_text

    mock_db = _make_mock_db(rowcount=7)
    now = dt.datetime.now(dt.UTC)

    result = await _purge_interaction_text(mock_db, now, days=7, batch=100)

    assert result == 7
    session = await mock_db.session.return_value.__aenter__()
    session.execute.assert_called()
    session.commit.assert_called()


@pytest.mark.asyncio
async def test_purge_request_content_returns_rowcount(monkeypatch):
    _stub_taskiq(monkeypatch)
    monkeypatch.setenv("TASKIQ_BROKER", "memory")
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_request_content

    mock_db = _make_mock_db(rowcount=4)
    now = dt.datetime.now(dt.UTC)

    result = await _purge_request_content(mock_db, now, days=7, batch=100)

    assert result == 4
    session = await mock_db.session.return_value.__aenter__()
    session.execute.assert_called()
    session.commit.assert_called()


@pytest.mark.asyncio
async def test_purge_idempotent_zero_rowcount(monkeypatch):
    _stub_taskiq(monkeypatch)
    monkeypatch.setenv("TASKIQ_BROKER", "memory")
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_crawl_content

    mock_db = _make_mock_db(rowcount=0)
    now = dt.datetime.now(dt.UTC)

    result = await _purge_crawl_content(mock_db, now, days=7, batch=100)

    assert result == 0
    session = await mock_db.session.return_value.__aenter__()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_purge_body_aggregates_subsystem_counts(monkeypatch):
    _stub_taskiq(monkeypatch)
    monkeypatch.setenv("TASKIQ_BROKER", "memory")
    _evict_app_tasks()

    from app.tasks.purge_raw_data import PurgeStats, _purge_body

    monkeypatch.setattr(
        "app.tasks.purge_raw_data._purge_telegram_raw",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        "app.tasks.purge_raw_data._purge_crawl_content",
        AsyncMock(return_value=2),
    )
    monkeypatch.setattr(
        "app.tasks.purge_raw_data._purge_llm_payload",
        AsyncMock(return_value=3),
    )
    monkeypatch.setattr(
        "app.tasks.purge_raw_data._purge_video_transcript",
        AsyncMock(return_value=4),
    )
    monkeypatch.setattr(
        "app.tasks.purge_raw_data._purge_interaction_text",
        AsyncMock(return_value=5),
    )
    monkeypatch.setattr(
        "app.tasks.purge_raw_data._purge_request_content",
        AsyncMock(return_value=6),
    )

    result = await _purge_body(_build_cfg(), MagicMock())

    assert result == PurgeStats(
        telegram_raw=1,
        crawl_content=2,
        llm_payload=3,
        video_transcript=4,
        interaction_text=5,
        request_content=6,
    )
