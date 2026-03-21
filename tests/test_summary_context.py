"""Tests for summary context builder."""

from __future__ import annotations

import json
import unittest

from app.domain.services.summary_context import build_summary_context


class TestBuildSummaryContext(unittest.TestCase):
    def test_basic_context(self) -> None:
        summary = {
            "json_payload": {
                "title": "Test",
                "summary_1000": "Content",
                "estimated_reading_time_min": 5,
                "source_type": "article",
                "topic_tags": ["ai"],
            },
            "lang": "en",
        }
        request = {"normalized_url": "https://example.com", "input_url": "https://example.com"}
        ctx = build_summary_context(summary, request)
        assert ctx["url"] == "https://example.com"
        assert ctx["title"] == "Test"
        assert ctx["language"] == "en"
        assert ctx["reading_time"] == 5
        assert ctx["source_type"] == "article"
        assert ctx["tags"] == ["ai"]
        assert ctx["content"] == "Content"

    def test_tag_names_override(self) -> None:
        summary = {"json_payload": {"topic_tags": ["old"]}, "lang": "en"}
        request = {"normalized_url": "https://x.com"}
        ctx = build_summary_context(summary, request, tag_names=["new1", "new2"])
        assert ctx["tags"] == ["new1", "new2"]

    def test_none_inputs(self) -> None:
        ctx = build_summary_context(None, None)
        assert ctx["url"] == ""
        assert ctx["title"] == ""
        assert ctx["tags"] == []
        assert ctx["language"] == ""
        assert ctx["reading_time"] == 0
        assert ctx["source_type"] == ""
        assert ctx["content"] == ""

    def test_json_string_payload(self) -> None:
        summary = {"json_payload": json.dumps({"title": "Parsed"}), "lang": "en"}
        ctx = build_summary_context(summary, None)
        assert ctx["title"] == "Parsed"

    def test_invalid_json_string_payload(self) -> None:
        summary = {"json_payload": "not valid json{{{", "lang": "en"}
        ctx = build_summary_context(summary, None)
        assert ctx["title"] == ""

    def test_url_falls_back_to_input_url(self) -> None:
        request = {"input_url": "https://fallback.com"}
        ctx = build_summary_context(None, request)
        assert ctx["url"] == "https://fallback.com"

    def test_normalized_url_preferred_over_input_url(self) -> None:
        request = {
            "normalized_url": "https://normalized.com",
            "input_url": "https://input.com",
        }
        ctx = build_summary_context(None, request)
        assert ctx["url"] == "https://normalized.com"

    def test_content_falls_back_to_summary_250(self) -> None:
        summary = {
            "json_payload": {"summary_250": "Short summary"},
            "lang": "en",
        }
        ctx = build_summary_context(summary, None)
        assert ctx["content"] == "Short summary"

    def test_summary_1000_preferred_over_250(self) -> None:
        summary = {
            "json_payload": {
                "summary_1000": "Long summary",
                "summary_250": "Short summary",
            },
            "lang": "en",
        }
        ctx = build_summary_context(summary, None)
        assert ctx["content"] == "Long summary"

    def test_empty_tag_names_uses_payload_tags(self) -> None:
        summary = {"json_payload": {"topic_tags": ["from_payload"]}, "lang": "en"}
        ctx = build_summary_context(summary, None, tag_names=[])
        # Empty list is falsy, so payload tags should be used
        assert ctx["tags"] == ["from_payload"]


if __name__ == "__main__":
    unittest.main()
