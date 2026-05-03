from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.adapters.digest.session_validator import validate_and_repair_session


def _make_session(tmp_path: Path, ddl: str, insert: str | None = None) -> Path:
    db = tmp_path / "test.session"
    with sqlite3.connect(db) as conn:
        conn.execute(ddl)
        if insert:
            conn.execute(insert)
        conn.commit()
    return db


def test_repairs_legacy_number_column(tmp_path: Path) -> None:
    db = _make_session(
        tmp_path,
        "CREATE TABLE version (number INTEGER PRIMARY KEY)",
        "INSERT INTO version VALUES (6)",
    )

    result = validate_and_repair_session(db)

    assert result == {"status": "repaired", "from": "number"}
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT version FROM version").fetchone()
    assert row is not None and row[0] == 6


def test_returns_ok_when_already_correct(tmp_path: Path) -> None:
    db = _make_session(
        tmp_path,
        "CREATE TABLE version (version INTEGER PRIMARY KEY)",
        "INSERT INTO version VALUES (6)",
    )

    result = validate_and_repair_session(db)

    assert result == {"status": "ok"}
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT version FROM version").fetchone()
    assert row is not None and row[0] == 6


def test_returns_absent_when_file_missing(tmp_path: Path) -> None:
    result = validate_and_repair_session(tmp_path / "nonexistent.session")
    assert result == {"status": "absent"}


def test_returns_incompatible_when_neither_column(tmp_path: Path) -> None:
    db = _make_session(tmp_path, "CREATE TABLE version (foo INTEGER PRIMARY KEY)")

    result = validate_and_repair_session(db)

    assert result["status"] == "incompatible"
    assert "foo" in result.get("columns", "")
