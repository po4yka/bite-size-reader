"""Tests for CLI output formatters."""

import json

from ratatoskr_cli.output import (
    format_aggregation_detail,
    format_aggregation_list,
    format_collections,
    format_json,
    format_summary_list,
    format_tags,
)


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


class TestFormatAggregationDetail:
    def test_human_output(self, capsys):
        data = {
            "session": {
                "id": 7,
                "status": "completed",
                "correlation_id": "corr-1",
                "total_items": 2,
                "successful_count": 2,
                "failed_count": 0,
                "duplicate_count": 0,
                "progress": {"processedItems": 2, "completionPercent": 100},
            },
            "items": [
                {
                    "position": 1,
                    "status": "extracted",
                    "source_kind": "url",
                    "url": "https://one.example",
                }
            ],
            "aggregation": {
                "overview": "Combined synthesis overview",
                "tldr": "Short summary",
                "key_ideas": ["First", "Second"],
            },
        }

        format_aggregation_detail(data)
        captured = capsys.readouterr()
        assert "Aggregation Session" in captured.out
        assert "Combined synthesis overview" in captured.out
        assert "Short summary" in captured.out
        assert "First" in captured.out

    def test_json_mode(self, capsys):
        data = {"session": {"id": 7}, "items": [], "aggregation": None}
        format_aggregation_detail(data, json_mode=True)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["session"]["id"] == 7


class TestFormatAggregationList:
    def test_empty_list(self, capsys):
        format_aggregation_list({"sessions": []})
        captured = capsys.readouterr()
        assert "No aggregation sessions" in captured.out

    def test_json_mode(self, capsys):
        data = {"sessions": [{"id": 1, "status": "completed"}]}
        format_aggregation_list(data, json_mode=True)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["sessions"][0]["id"] == 1
