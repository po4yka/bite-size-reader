from __future__ import annotations

from typing import Any

from app.cli import healthcheck


class _FakeConfig:
    pass


def test_healthcheck_returns_zero_after_success(monkeypatch) -> None:
    calls: list[str] = []

    class _Database:
        def __init__(self, *, config: Any) -> None:
            assert isinstance(config, _FakeConfig)

        async def healthcheck(self) -> None:
            calls.append("healthcheck")

        async def dispose(self) -> None:
            calls.append("dispose")

    monkeypatch.setattr(healthcheck, "DatabaseConfig", _FakeConfig)
    monkeypatch.setattr(healthcheck, "Database", _Database)

    assert healthcheck.main() == 0
    assert calls == ["healthcheck", "dispose"]


def test_healthcheck_returns_one_after_failure(monkeypatch, capsys) -> None:
    calls: list[str] = []

    class _Database:
        def __init__(self, *, config: Any) -> None:
            assert isinstance(config, _FakeConfig)

        async def healthcheck(self) -> None:
            calls.append("healthcheck")
            raise RuntimeError("offline")

        async def dispose(self) -> None:
            calls.append("dispose")

    monkeypatch.setattr(healthcheck, "DatabaseConfig", _FakeConfig)
    monkeypatch.setattr(healthcheck, "Database", _Database)

    assert healthcheck.main() == 1
    assert calls == ["healthcheck", "dispose"]
    assert "database healthcheck failed: offline" in capsys.readouterr().err
