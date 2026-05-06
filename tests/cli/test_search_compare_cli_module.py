from __future__ import annotations

from app.cli import search_compare


def test_print_comparison_renders_sections(capsys) -> None:
    search_compare.print_comparison({"fts": [], "vector": [], "hybrid": []}, "test query")
    out = capsys.readouterr().out

    assert "SEARCH COMPARISON" in out
    assert "Query: 'test query'" in out
    assert "FTS (Full-Text):" in out


async def test_main_returns_zero_for_help(monkeypatch) -> None:
    monkeypatch.setattr(search_compare.sys, "argv", ["search_compare.py", "--help"])

    assert await search_compare.main() == 0


async def test_main_rejects_legacy_db_option(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        search_compare.sys,
        "argv",
        ["search_compare.py", "semantic query", "--db=/tmp/missing.sqlite"],
    )

    assert await search_compare.main() == 1
    assert "--db is no longer supported" in capsys.readouterr().out
