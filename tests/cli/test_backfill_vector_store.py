from __future__ import annotations

from app.cli import backfill_vector_store


def test_main_returns_zero_for_help(monkeypatch, capsys) -> None:
    monkeypatch.setattr(backfill_vector_store.sys, "argv", ["backfill_vector_store.py", "--help"])

    assert backfill_vector_store.main() == 0
    assert "--dsn=DSN" in capsys.readouterr().out


def test_main_rejects_legacy_db_option(monkeypatch) -> None:
    monkeypatch.setattr(
        backfill_vector_store.sys,
        "argv",
        ["backfill_vector_store.py", "--db=/tmp/ratatoskr.db"],
    )

    assert backfill_vector_store.main() == 1
