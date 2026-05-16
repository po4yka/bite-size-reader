from __future__ import annotations

import sys
from typing import Any

from app.cli import migrate_db as migrate_cli


_PG_DSN = "postgresql+asyncpg://user:pass@localhost:5432/test"


def test_main_runs_shared_migration_flow_once(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_upgrade_to_head(db_path: str) -> None:
        captured["db_path"] = db_path
        captured["calls"] = captured.get("calls", 0) + 1

    monkeypatch.setattr(migrate_cli, "upgrade_to_head", _fake_upgrade_to_head)
    monkeypatch.setattr(sys, "argv", ["migrate_db", _PG_DSN])

    rc = migrate_cli.main()

    assert rc == 0
    assert captured["db_path"] == _PG_DSN
    assert captured["calls"] == 1


def test_migrate_db_status_reports_migration_state(monkeypatch, capsys) -> None:
    def _fake_print_status(path: str) -> None:
        print("Migration Status:")
        print("Pending: 0")

    monkeypatch.setattr(migrate_cli, "print_status", _fake_print_status)
    monkeypatch.setattr(sys, "argv", ["migrate_db", "--status", _PG_DSN])

    assert migrate_cli.main() == 0

    output = capsys.readouterr().out
    assert "Migration Status:" in output
    assert "Pending:" in output
