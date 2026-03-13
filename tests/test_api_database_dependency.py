from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("chromadb.config", MagicMock())
sys.modules.setdefault("chromadb.errors", MagicMock())

from app.api.dependencies import database as database_dependency


def test_get_session_manager_runs_migrations_once(monkeypatch, tmp_path) -> None:
    captured: dict[str, Any] = {}

    class _FakeDatabaseSessionManager:
        def __init__(self, **kwargs) -> None:
            captured["kwargs"] = kwargs
            self.migrate_calls = 0

        def migrate(self) -> None:
            self.migrate_calls += 1

    monkeypatch.setattr(database_dependency, "_session_manager", None)
    monkeypatch.setattr(database_dependency, "DatabaseSessionManager", _FakeDatabaseSessionManager)
    monkeypatch.setattr(
        database_dependency,
        "_get_db_config",
        lambda: SimpleNamespace(
            operation_timeout=30.0,
            max_retries=3,
            json_max_size=10_000_000,
            json_max_depth=20,
            json_max_array_length=10_000,
            json_max_dict_keys=1_000,
        ),
    )
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))

    manager = cast("_FakeDatabaseSessionManager", database_dependency.get_session_manager())
    same_manager = database_dependency.get_session_manager()
    kwargs = cast("dict[str, Any]", captured["kwargs"])

    assert same_manager is manager
    assert manager.migrate_calls == 1
    assert kwargs["path"] == str(tmp_path / "app.db")

    monkeypatch.setattr(database_dependency, "_session_manager", None)
