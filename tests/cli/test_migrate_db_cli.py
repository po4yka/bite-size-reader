from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from app.cli import migrate_db as migrate_cli

if TYPE_CHECKING:
    from pathlib import Path


def test_main_runs_shared_migration_flow_once(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeDatabaseSessionManager:
        def __init__(self, *, path: str) -> None:
            captured["path"] = path
            captured["db"] = self
            self.migrate_calls = 0

        def migrate(self) -> None:
            self.migrate_calls += 1

    monkeypatch.setattr(migrate_cli, "DatabaseSessionManager", _FakeDatabaseSessionManager)
    monkeypatch.setattr(sys, "argv", ["migrate_db", "/tmp/test.db"])

    rc = migrate_cli.main()

    assert rc == 0
    assert captured["path"] == "/tmp/test.db"
    assert captured["db"].migrate_calls == 1


def test_migrate_db_status_reports_migration_state(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    db_path = tmp_path / "status.sqlite"
    monkeypatch.setattr(sys, "argv", ["migrate_db", "--status", str(db_path)])

    assert migrate_cli.main() == 0

    output = capsys.readouterr().out
    assert "Migration Status:" in output
    assert "Pending:" in output
