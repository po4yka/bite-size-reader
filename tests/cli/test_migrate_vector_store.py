from __future__ import annotations

from app.cli import migrate_vector_store


def test_main_returns_zero_for_help(monkeypatch, capsys) -> None:
    monkeypatch.setattr(migrate_vector_store.sys, "argv", ["migrate_vector_store.py", "--help"])

    assert migrate_vector_store.main() == 0
    assert "--dsn=DSN" in capsys.readouterr().out


def test_main_rejects_legacy_db_option(monkeypatch) -> None:
    monkeypatch.setattr(
        migrate_vector_store.sys,
        "argv",
        ["migrate_vector_store.py", "--db=/tmp/ratatoskr.db"],
    )

    assert migrate_vector_store.main() == 1
