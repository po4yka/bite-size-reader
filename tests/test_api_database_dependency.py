from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from app.api.dependencies import database as database_dependency
from app.di import database as di_database


def test_get_session_manager_runs_migrations_once(monkeypatch, tmp_path) -> None:
    captured: dict[str, Any] = {}

    class _FakeDatabase:
        def __init__(self, *, config: Any) -> None:
            captured["config"] = config
            self.config = config
            self.migrate_calls = 0

        async def migrate(self) -> None:
            self.migrate_calls += 1

        async def dispose(self) -> None:
            pass

    di_database.clear_cached_runtime_database()
    monkeypatch.setattr(
        database_dependency,
        "resolve_api_runtime",
        lambda request=None: (_ for _ in ()).throw(RuntimeError("runtime not ready")),
    )
    monkeypatch.setattr(di_database, "Database", _FakeDatabase)
    config = SimpleNamespace(dsn=f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setattr(
        di_database,
        "_get_env_db_config",
        lambda: config,
    )

    manager = cast("_FakeDatabase", database_dependency.get_session_manager())
    same_manager = database_dependency.get_session_manager()

    assert same_manager is manager
    assert manager.migrate_calls == 1
    assert captured["config"] is config

    di_database.clear_cached_runtime_database()
