from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _build_cfg(
    *, karakeep_enabled: bool = True, digest_enabled: bool = True, allowed_user_ids=(123,)
):
    return SimpleNamespace(
        karakeep=SimpleNamespace(
            enabled=karakeep_enabled,
            api_key="kk-key",
            auto_sync_enabled=True,
            sync_interval_hours=6,
        ),
        digest=SimpleNamespace(
            enabled=digest_enabled,
            digest_times=["09:30", "18:45"],
            timezone="UTC",
        ),
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
        def __init__(self, *, hours: int) -> None:
            self.hours = hours

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
        "karakeep_service_factory": MagicMock(),
        "karakeep_user_id_resolver": MagicMock(return_value=123),
        "digest_userbot_factory": MagicMock(),
        "digest_llm_factory": MagicMock(),
        "digest_bot_client_factory": MagicMock(),
        "digest_service_factory": MagicMock(),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_start_stop_and_next_run_time(monkeypatch) -> None:
    scheduler_module, FakeCronTrigger, FakeIntervalTrigger = _load_scheduler_module(monkeypatch)
    service = scheduler_module.SchedulerService(
        _build_cfg(),
        db=MagicMock(),
        deps=_minimal_deps(),
    )

    service.start()

    assert service.is_running is True
    assert isinstance(service._scheduler.jobs["karakeep_sync"]["trigger"], FakeIntervalTrigger)
    assert isinstance(service._scheduler.jobs["channel_digest_0"]["trigger"], FakeCronTrigger)
    assert service._scheduler.jobs["channel_digest_0"]["trigger"].hour == 9
    assert service._scheduler.jobs["channel_digest_1"]["trigger"].minute == 45
    assert service.get_next_run_time("karakeep_sync") == datetime(2026, 1, 1, 9, 0, 0)
    assert service.get_next_run_time("missing") is None

    service.stop()

    assert service.is_running is False


@pytest.mark.asyncio
async def test_run_karakeep_sync_uses_first_allowed_user(monkeypatch) -> None:
    scheduler_module, _, _ = _load_scheduler_module(monkeypatch)
    sync_service = MagicMock()
    sync_service.run_full_sync = AsyncMock(
        return_value=SimpleNamespace(
            bsr_to_karakeep=SimpleNamespace(
                items_synced=1, items_skipped=2, items_failed=0, errors=[]
            ),
            karakeep_to_bsr=SimpleNamespace(
                items_synced=3, items_skipped=4, items_failed=0, errors=[]
            ),
            total_duration_seconds=12.5,
        )
    )
    service = scheduler_module.SchedulerService(
        _build_cfg(allowed_user_ids=(42, 99)),
        db=MagicMock(),
        deps=_minimal_deps(
            karakeep_service_factory=MagicMock(return_value=sync_service),
            karakeep_user_id_resolver=MagicMock(return_value=42),
        ),
    )

    await service._run_karakeep_sync()

    sync_service.run_full_sync.assert_awaited_once_with(user_id=42)


@pytest.mark.asyncio
async def test_run_karakeep_sync_returns_early_without_allowed_user(monkeypatch) -> None:
    scheduler_module, _, _ = _load_scheduler_module(monkeypatch)
    sync_service = MagicMock()
    sync_service.run_full_sync = AsyncMock()
    service = scheduler_module.SchedulerService(
        _build_cfg(allowed_user_ids=()),
        db=MagicMock(),
        deps=_minimal_deps(
            karakeep_service_factory=MagicMock(return_value=sync_service),
            karakeep_user_id_resolver=MagicMock(return_value=None),
        ),
    )

    await service._run_karakeep_sync()

    sync_service.run_full_sync.assert_not_awaited()


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
