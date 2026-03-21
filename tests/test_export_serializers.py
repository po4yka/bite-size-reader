"""Tests for export serializers (JSON, CSV, Netscape HTML)."""

from __future__ import annotations

import csv
import io
import json
import unittest

from app.domain.services.import_export.export_serializers import (
    CsvExporter,
    JsonExporter,
    NetscapeHtmlExporter,
)


def _sample_summaries() -> list[dict]:
    return [
        {
            "url": "https://example.com/article1",
            "title": "Test Article 1",
            "tags": [{"name": "python"}, {"name": "tutorial"}],
            "language": "en",
            "created_at": "2024-01-15T10:00:00Z",
            "is_read": True,
            "is_favorited": False,
        },
        {
            "url": "https://example.com/article2",
            "title": "Test Article 2",
            "tags": ["news"],
            "language": "en",
            "created_at": "2024-02-20T14:00:00Z",
            "is_read": False,
            "is_favorited": True,
        },
    ]


class TestJsonExporter(unittest.TestCase):
    def setUp(self) -> None:
        self.output = JsonExporter.serialize(_sample_summaries())
        self.data = json.loads(self.output)

    def test_valid_json(self) -> None:
        assert isinstance(self.data, dict)

    def test_contains_version(self) -> None:
        assert self.data["version"] == 1

    def test_contains_exported_at(self) -> None:
        assert "exported_at" in self.data
        assert isinstance(self.data["exported_at"], str)

    def test_contains_summaries(self) -> None:
        assert "summaries" in self.data
        assert len(self.data["summaries"]) == 2

    def test_summary_fields(self) -> None:
        s = self.data["summaries"][0]
        assert s["url"] == "https://example.com/article1"
        assert s["title"] == "Test Article 1"
        assert "python" in s["tags"]
        assert "tutorial" in s["tags"]

    def test_empty_summaries(self) -> None:
        output = JsonExporter.serialize([])
        data = json.loads(output)
        assert data["summaries"] == []

    def test_contains_tags_and_collections_keys(self) -> None:
        assert "tags" in self.data
        assert "collections" in self.data


class TestCsvExporter(unittest.TestCase):
    def setUp(self) -> None:
        self.output = CsvExporter.serialize(_sample_summaries())
        self.reader = csv.DictReader(io.StringIO(self.output))
        self.rows = list(self.reader)

    def test_valid_csv(self) -> None:
        assert len(self.rows) == 2

    def test_correct_headers(self) -> None:
        expected = {"url", "title", "tags", "language", "created_at", "is_read", "is_favorited"}
        assert expected == set(self.reader.fieldnames or [])

    def test_tags_joined_with_semicolons(self) -> None:
        row = self.rows[0]
        assert row["tags"] == "python;tutorial"

    def test_url_and_title(self) -> None:
        row = self.rows[0]
        assert row["url"] == "https://example.com/article1"
        assert row["title"] == "Test Article 1"

    def test_empty_summaries(self) -> None:
        output = CsvExporter.serialize([])
        reader = csv.DictReader(io.StringIO(output))
        rows = list(reader)
        assert rows == []


class TestNetscapeHtmlExporter(unittest.TestCase):
    def setUp(self) -> None:
        self.output = NetscapeHtmlExporter.serialize(_sample_summaries())

    def test_contains_doctype(self) -> None:
        assert "<!DOCTYPE NETSCAPE-Bookmark-file-1>" in self.output

    def test_contains_html_structure(self) -> None:
        assert "<TITLE>Bookmarks</TITLE>" in self.output
        assert "<H1>Bookmarks</H1>" in self.output
        assert "<DL><p>" in self.output
        assert "</DL><p>" in self.output

    def test_contains_href(self) -> None:
        assert 'HREF="https://example.com/article1"' in self.output
        assert 'HREF="https://example.com/article2"' in self.output

    def test_contains_add_date(self) -> None:
        assert "ADD_DATE=" in self.output

    def test_contains_tags(self) -> None:
        assert "TAGS=" in self.output
        assert "python" in self.output

    def test_empty_summaries(self) -> None:
        output = NetscapeHtmlExporter.serialize([])
        assert "<!DOCTYPE NETSCAPE-Bookmark-file-1>" in output
        assert "<DL><p>" in output


if __name__ == "__main__":
    unittest.main()
