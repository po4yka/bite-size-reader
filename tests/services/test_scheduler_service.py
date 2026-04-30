from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _build_cfg(*, digest_enabled: bool = True, rss_enabled: bool = False, allowed_user_ids=(123,)):
    return SimpleNamespace(
        digest=SimpleNamespace(
            enabled=digest_enabled,
            digest_times=["09:30", "18:45"],
            timezone="UTC",
        ),
        rss=SimpleNamespace(
            enabled=rss_enabled,
            poll_interval_minutes=60,
            auto_summarize=True,
            max_items_per_poll=20,
        ),
        signal_ingestion=SimpleNamespace(enabled=False, any_enabled=False),
        telegram=SimpleNamespace(
            allowed_user_ids=list(allowed_user_ids),
            api_id=1,
            api_hash="hash",
            bot_token="123:token",
        ),
    )


def _load_scheduler_module(monkeypatch):
    class FakeJob:
        def __init__(self, next_run_time: datetime | None = None) -> None:
            self.next_run_time = next_run_time or datetime(2026, 1, 1, 9, 0, 0)

    class FakeAsyncIOScheduler:
        def __init__(self) -> None:
            self.jobs: dict[str, dict[str, object]] = {}
            self.started = False
            self.shutdown_called_with: bool | None = None

        def add_job(self, func, trigger, id, name, replace_existing, max_instances) -> None:
            self.jobs[id] = {
                "func": func,
                "trigger": trigger,
                "name": name,
                "replace_existing": replace_existing,
                "max_instances": max_instances,
                "job": FakeJob(),
            }

        def start(self) -> None:
            self.started = True

        def shutdown(self, wait: bool = True) -> None:
            self.shutdown_called_with = wait

        def get_job(self, job_id: str):
            entry = self.jobs.get(job_id)
            return entry["job"] if entry else None

    class FakeIntervalTrigger:
        def __init__(self, *, hours: int = 0, minutes: int = 0) -> None:
            self.hours = hours
            self.minutes = minutes

    class FakeCronTrigger:
        def __init__(self, *, hour: int, minute: int, timezone: str) -> None:
            self.hour = hour
            self.minute = minute
            self.timezone = timezone

    monkeypatch.setitem(sys.modules, "apscheduler", types.ModuleType("apscheduler"))
    monkeypatch.setitem(
        sys.modules, "apscheduler.schedulers", types.ModuleType("apscheduler.schedulers")
    )
    scheduler_asyncio = types.ModuleType("apscheduler.schedulers.asyncio")
    scheduler_asyncio.AsyncIOScheduler = FakeAsyncIOScheduler
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.asyncio", scheduler_asyncio)
    monkeypatch.setitem(
        sys.modules, "apscheduler.triggers", types.ModuleType("apscheduler.triggers")
    )
    trigger_cron = types.ModuleType("apscheduler.triggers.cron")
    trigger_cron.CronTrigger = FakeCronTrigger
    monkeypatch.setitem(sys.modules, "apscheduler.triggers.cron", trigger_cron)
    trigger_interval = types.ModuleType("apscheduler.triggers.interval")
    trigger_interval.IntervalTrigger = FakeIntervalTrigger
    monkeypatch.setitem(sys.modules, "apscheduler.triggers.interval", trigger_interval)

    sys.modules.pop("app.infrastructure.scheduler.service", None)
    module = importlib.import_module("app.infrastructure.scheduler.service")
    return module, FakeCronTrigger, FakeIntervalTrigger


def _minimal_deps(**overrides):
    base = {
        "digest_userbot_factory": MagicMock(),
        "digest_llm_factory": MagicMock(),
        "digest_bot_client_factory": MagicMock(),
        "digest_service_factory": MagicMock(),
        "signal_worker_factory": None,
        "source_ingestion_runner_factory": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_start_stop_and_next_run_time(monkeypatch) -> None:
    scheduler_module, FakeCronTrigger, _FakeIntervalTrigger = _load_scheduler_module(monkeypatch)
    service = scheduler_module.SchedulerService(
        _build_cfg(),
        db=MagicMock(),
        deps=_minimal_deps(),
    )

    service.start()

    assert service.is_running is True
    assert isinstance(service._scheduler.jobs["channel_digest_0"]["trigger"], FakeCronTrigger)
    assert service._scheduler.jobs["channel_digest_0"]["trigger"].hour == 9
    assert service._scheduler.jobs["channel_digest_1"]["trigger"].minute == 45
    assert service.get_next_run_time("missing") is None

    service.stop()

    assert service.is_running is False


@pytest.mark.asyncio
async def test_run_channel_digest_starts_and_stops_dependencies(monkeypatch) -> None:
    scheduler_module, _, _ = _load_scheduler_module(monkeypatch)

    class FakeUserbot:
        def __init__(self) -> None:
            self.start = AsyncMock()
            self.stop = AsyncMock()

    class FakeLLMClient:
        def __init__(self) -> None:
            self.aclose = AsyncMock()

    class FakeBotClient:
        def __init__(self) -> None:
            self.send_message = AsyncMock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeDigestService:
        def get_users_with_subscriptions(self):
            return [1001, 1002]

        async def generate_digest(self, **kwargs):
            if kwargs["user_id"] == 1002:
                raise RuntimeError("user failure")
            return SimpleNamespace(post_count=3, errors=["minor"])

    userbot = FakeUserbot()
    llm_client = FakeLLMClient()
    bot_client = FakeBotClient()
    digest_service = FakeDigestService()
    service = scheduler_module.SchedulerService(
        _build_cfg(),
        db=MagicMock(),
        deps=_minimal_deps(
            digest_userbot_factory=MagicMock(return_value=userbot),
            digest_llm_factory=MagicMock(return_value=llm_client),
            digest_bot_client_factory=MagicMock(return_value=bot_client),
            digest_service_factory=MagicMock(return_value=digest_service),
        ),
    )

    await service._run_channel_digest()

    userbot.start.assert_awaited_once()
    userbot.stop.assert_awaited_once()
    llm_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_rss_poll_invokes_signal_worker(monkeypatch) -> None:
    scheduler_module, _, _ = _load_scheduler_module(monkeypatch)
    monkeypatch.setitem(
        sys.modules,
        "app.adapters.rss.feed_poller",
        SimpleNamespace(poll_all_feeds=AsyncMock(return_value={"new_item_ids": [], "new_items": 0})),
    )
    signal_worker = SimpleNamespace(run_once=AsyncMock(return_value={"persisted": 2}))
    service = scheduler_module.SchedulerService(
        _build_cfg(digest_enabled=False, rss_enabled=True),
        db=MagicMock(),
        deps=_minimal_deps(signal_worker_factory=MagicMock(return_value=signal_worker)),
    )

    await service._run_rss_poll()

    signal_worker.run_once.assert_awaited_once_with(limit=20)


@pytest.mark.asyncio
async def test_run_rss_poll_invokes_optional_source_ingestion_runner(monkeypatch) -> None:
    scheduler_module, _, _ = _load_scheduler_module(monkeypatch)
    monkeypatch.setitem(
        sys.modules,
        "app.adapters.rss.feed_poller",
        SimpleNamespace(poll_all_feeds=AsyncMock(return_value={"new_item_ids": [], "new_items": 0})),
    )
    runner = SimpleNamespace(run_once=AsyncMock(return_value={"items": 3}))
    service = scheduler_module.SchedulerService(
        _build_cfg(digest_enabled=False, rss_enabled=True),
        db=MagicMock(),
        deps=_minimal_deps(source_ingestion_runner_factory=MagicMock(return_value=runner)),
    )

    await service._run_rss_poll()

    runner.run_once.assert_awaited_once_with()
