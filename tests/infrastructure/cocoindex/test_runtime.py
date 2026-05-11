"""Tests for CocoIndex runtime flow lifecycle."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest


class _FakeFlow:
    def __init__(self, name: str) -> None:
        self.name = name
        self.setup_calls = 0
        self.update_calls = 0

    def setup(self) -> None:
        self.setup_calls += 1

    def update(self) -> None:
        self.update_calls += 1


class _FakeUpdater:
    instances: list[_FakeUpdater] = []

    def __init__(self, flow: _FakeFlow, _options: object) -> None:
        self.flow = flow
        self.entered = False
        self.exited = False
        self.__class__.instances.append(self)

    def __enter__(self) -> _FakeUpdater:
        self.entered = True
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.exited = True


@pytest.mark.asyncio
async def test_runtime_starts_updates_and_stops_all_flows(monkeypatch) -> None:
    fake_cocoindex = types.SimpleNamespace(
        Settings=lambda **kwargs: kwargs,
        init=lambda _settings: None,
        FlowLiveUpdater=_FakeUpdater,
        FlowLiveUpdaterOptions=lambda **kwargs: kwargs,
    )
    monkeypatch.setitem(sys.modules, "cocoindex", fake_cocoindex)
    _FakeUpdater.instances = []

    summary_flow = _FakeFlow("summaries")
    repo_flow = _FakeFlow("repositories")

    import app.infrastructure.cocoindex.flow as flow_module

    monkeypatch.setattr(flow_module, "build_summaries_flow", lambda **_kwargs: summary_flow)
    monkeypatch.setattr(flow_module, "build_repositories_flow", lambda **_kwargs: repo_flow)

    from app.infrastructure.cocoindex.runtime import CocoIndexRuntime

    cfg = SimpleNamespace(
        cocoindex=SimpleNamespace(
            dsn_override=None,
            listen_notify_channel="ratatoskr_summaries_changed",
        ),
        database=SimpleNamespace(dsn="postgresql+asyncpg://user:pass@localhost/db"),
        vector_store=SimpleNamespace(
            url="http://localhost:6333",
            api_key=None,
            user_scope="public",
            environment="test",
        ),
    )
    runtime = CocoIndexRuntime(cfg=cfg, collection_name="notes_test_public_v1")

    await runtime.start()
    await runtime.run_one_shot()
    await runtime.stop()

    assert summary_flow.setup_calls == 1
    assert repo_flow.setup_calls == 1
    assert summary_flow.update_calls == 1
    assert repo_flow.update_calls == 1
    assert len(_FakeUpdater.instances) == 2
    assert all(updater.entered and updater.exited for updater in _FakeUpdater.instances)
