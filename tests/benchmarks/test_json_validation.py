"""Performance benchmarks for JSON validation operations.

Target: p99 latency < 10ms for summary JSON validation.

These tests ensure JSON validation remains performant as the schema evolves.
"""

from __future__ import annotations

import json

import pytest

pytest_benchmark = pytest.importorskip("pytest_benchmark")


class TestJSONValidationBenchmarks:
    """Benchmarks for JSON validation functions."""

    @pytest.fixture
    def valid_summary_json(self) -> dict:
        """Generate a valid summary JSON for benchmarking."""
        return {
            "summary_250": "This is a short summary of the article content.",
            "summary_1000": (
                "This is a longer summary that provides more detail about the article. "
                "It covers the main points discussed and gives readers a comprehensive "
                "understanding of what the article is about. The summary includes key facts "
                "and important context."
            ),
            "tldr": "Key takeaway from the article in a concise format.",
            "key_ideas": [
                "First key idea from the content",
                "Second key idea with details",
                "Third important concept",
                "Fourth insight worth noting",
                "Fifth conclusion or takeaway",
            ],
            "topic_tags": ["#technology", "#ai", "#automation"],
            "entities": {
                "people": ["John Doe", "Jane Smith"],
                "organizations": ["Acme Corp", "Tech Inc"],
                "locations": ["San Francisco", "New York"],
            },
            "estimated_reading_time_min": 7,
            "key_stats": [
                {
                    "label": "Revenue Growth",
                    "value": 25.5,
                    "unit": "percent",
                    "source_excerpt": "Revenue grew by 25.5% year over year",
                }
            ],
            "answered_questions": [
                "What is the main topic?",
                "How does it affect users?",
                "What are the implications?",
            ],
            "readability": {
                "method": "Flesch-Kincaid",
                "score": 12.4,
                "level": "College",
            },
            "seo_keywords": ["artificial intelligence", "machine learning", "automation"],
        }

    @pytest.fixture
    def malformed_summary_json(self) -> dict:
        """Generate a malformed summary JSON for testing error paths."""
        return {
            "summary_250": "x" * 300,  # Too long
            "summary_1000": "",  # Empty
            "tldr": "",
            "key_ideas": [],  # Empty
            "topic_tags": ["tag1", "tag2"],  # Missing #
            "entities": {
                "people": ["John Doe", "john doe"],  # Duplicate
                "organizations": [],
                "locations": [],
            },
            "estimated_reading_time_min": -1,  # Invalid
        }

    def test_validate_and_shape_throughput(self, benchmark, valid_summary_json: dict) -> None:
        """Benchmark valid summary validation throughput."""
        from app.core.summary_contract import validate_and_shape_summary

        def validate_batch():
            for _ in range(100):
                validate_and_shape_summary(valid_summary_json)

        benchmark(validate_batch)

        # Calculate latency per validation
        latency_ms = (benchmark.stats.stats.mean * 1000) / 100

        # p99 should be < 10ms (mean * ~2.3 for normal distribution)
        estimated_p99 = latency_ms * 2.3
        assert estimated_p99 < 10, f"JSON validation p99 too high: {estimated_p99:.2f}ms"

    def test_json_parsing_throughput(self, benchmark, valid_summary_json: dict) -> None:
        """Benchmark JSON parsing throughput."""
        json_string = json.dumps(valid_summary_json)

        def parse_batch():
            for _ in range(1000):
                json.loads(json_string)

        benchmark(parse_batch)

        mean = benchmark.stats.stats.mean
        ops_per_sec = (1000 / mean) if mean > 0 else 0

        assert ops_per_sec > 10000, f"JSON parsing too slow: {ops_per_sec:.0f} ops/sec"

    def test_json_schema_retrieval(self, benchmark) -> None:
        """Benchmark JSON schema retrieval."""
        from app.core.summary_contract import get_summary_json_schema

        def get_schema_batch():
            for _ in range(1000):
                get_summary_json_schema()

        benchmark(get_schema_batch)

        mean = benchmark.stats.stats.mean
        ops_per_sec = (1000 / mean) if mean > 0 else 0

        # Schema retrieval should be fast (cached or simple dict)
        # Threshold tuned for Raspberry Pi 5 ARM; x86 typically 10x higher
        assert ops_per_sec > 40, f"Schema retrieval too slow: {ops_per_sec:.0f} ops/sec"
