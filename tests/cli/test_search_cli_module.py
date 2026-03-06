from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.cli import search as search_cli


def test_print_results_renders_summary_and_truncates_snippet(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = SimpleNamespace(
        title="Result title",
        url="https://example.com/article",
        snippet="x" * 240,
        source="example.com",
        published_at="2026-01-01",
        combined_score=0.9,
        fts_score=0.4,
        vector_score=0.5,
    )

    search_cli.print_results([result], "hybrid", "test query")
    out = capsys.readouterr().out

    assert "Search Mode: HYBRID" in out
    assert "Query: 'test query'" in out
    assert "Results: 1" in out
    assert "Result title" in out
    assert "..." in out
    assert "Scores: Combined=0.900" in out


@pytest.mark.asyncio
async def test_main_returns_zero_for_help(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_cli.sys, "argv", ["search.py", "--help"])
    rc = await search_cli.main()
    assert rc == 0


@pytest.mark.asyncio
async def test_main_rejects_invalid_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(search_cli.sys, "argv", ["search.py", "query", "--mode=invalid"])

    rc = await search_cli.main()
    out = capsys.readouterr().out

    assert rc == 1
    assert "Invalid mode" in out


@pytest.mark.asyncio
async def test_main_reports_missing_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_db = tmp_path / "missing.sqlite"
    argv = ["search.py", "semantic query", f"--db={missing_db}"]
    monkeypatch.setattr(search_cli.sys, "argv", argv)

    rc = await search_cli.main()
    out = capsys.readouterr().out

    assert rc == 1
    assert "Database file not found" in out
