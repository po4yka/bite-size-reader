"""Unit tests for MarkitdownExtractor."""

from __future__ import annotations

import sys
from pathlib import Path  # noqa: TC003

import pytest

markitdown = pytest.importorskip("markitdown", reason="markitdown not installed")

from app.adapters.attachment.markitdown_extractor import DocumentContent, MarkitdownExtractor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_extract_html_returns_markdown(tmp_path: Path) -> None:
    html = "<h1>Title</h1><p>Body paragraph with some text.</p>"
    p = _write(tmp_path, "page.html", html)

    result = MarkitdownExtractor.extract(p, file_format="html")

    assert isinstance(result, DocumentContent)
    assert result.file_format == "html"
    assert "Title" in result.text
    assert result.truncated is False


def test_extract_csv_returns_table_content(tmp_path: Path) -> None:
    csv_content = "name,age,city\nAlice,30,Berlin\nBob,25,Paris\n"
    p = _write(tmp_path, "data.csv", csv_content)

    result = MarkitdownExtractor.extract(p, file_format="csv")

    assert "Alice" in result.text or "name" in result.text
    assert result.truncated is False


def test_extract_json_returns_text(tmp_path: Path) -> None:
    json_content = '{"key": "value", "number": 42}'
    p = _write(tmp_path, "data.json", json_content)

    result = MarkitdownExtractor.extract(p, file_format="json")

    assert result.text  # non-empty
    assert result.file_format == "json"


def test_extract_truncates_long_input(tmp_path: Path) -> None:
    # markitdown converts HTML to text; write a very large HTML body
    long_body = "A" * 60_000
    html = f"<html><body><p>{long_body}</p></body></html>"
    p = _write(tmp_path, "large.html", html)
    max_chars = 45_000

    result = MarkitdownExtractor.extract(p, file_format="html", max_chars=max_chars)

    assert result.truncated is True
    assert len(result.text) <= max_chars


def test_extract_raises_on_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "no_such_file.docx"
    with pytest.raises(ValueError, match="not found"):
        MarkitdownExtractor.extract(missing, file_format="docx")


def test_extract_raises_when_markitdown_missing(tmp_path: Path) -> None:
    p = _write(tmp_path, "page.html", "<p>hello</p>")
    original = sys.modules.get("markitdown")
    try:
        sys.modules["markitdown"] = None
        with pytest.raises(ValueError, match="markitdown"):
            MarkitdownExtractor.extract(p, file_format="html")
    finally:
        if original is None:
            sys.modules.pop("markitdown", None)
        else:
            sys.modules["markitdown"] = original


def test_extract_docx_if_python_docx_available(tmp_path: Path) -> None:
    docx = pytest.importorskip("docx", reason="python-docx not installed")
    doc = docx.Document()
    doc.add_paragraph("Hello from a DOCX fixture.")
    docx_path = tmp_path / "test.docx"
    doc.save(str(docx_path))

    result = MarkitdownExtractor.extract(docx_path, file_format="docx")

    assert "Hello" in result.text
    assert result.file_format == "docx"
    assert result.truncated is False
