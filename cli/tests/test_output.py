"""Tests for CLI output formatters."""

import json

from bsr_cli.output import format_collections, format_json, format_summary_list, format_tags


class TestFormatJson:
    def test_produces_valid_json(self, capsys):
        format_json({"key": "value", "count": 42})
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["key"] == "value"

    def test_handles_nested_data(self, capsys):
        format_json({"items": [1, 2, 3], "nested": {"a": True}})
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["items"] == [1, 2, 3]
        assert parsed["nested"]["a"] is True


class TestFormatSummaryList:
    def test_empty_list(self, capsys):
        format_summary_list({"summaries": []})
        captured = capsys.readouterr()
        assert "No summaries" in captured.out

    def test_json_mode(self, capsys):
        data = {"summaries": [{"id": 1, "title": "Test"}]}
        format_summary_list(data, json_mode=True)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "summaries" in parsed

    def test_empty_plain_list(self, capsys):
        format_summary_list([])
        captured = capsys.readouterr()
        assert "No summaries" in captured.out


class TestFormatTags:
    def test_empty_tags(self, capsys):
        format_tags({"tags": []})
        captured = capsys.readouterr()
        assert "No tags" in captured.out

    def test_json_mode(self, capsys):
        data = {"tags": [{"id": 1, "name": "python"}]}
        format_tags(data, json_mode=True)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "tags" in parsed

    def test_empty_plain_list(self, capsys):
        format_tags([])
        captured = capsys.readouterr()
        assert "No tags" in captured.out


class TestFormatCollections:
    def test_empty_collections(self, capsys):
        format_collections({"collections": []})
        captured = capsys.readouterr()
        assert "No collections" in captured.out

    def test_json_mode(self, capsys):
        data = {"collections": [{"id": 1, "name": "Favorites"}]}
        format_collections(data, json_mode=True)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "collections" in parsed

    def test_empty_plain_list(self, capsys):
        format_collections([])
        captured = capsys.readouterr()
        assert "No collections" in captured.out
