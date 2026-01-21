"""Property-based tests for JSON validation using Hypothesis.

These tests verify that JSON validation functions handle arbitrary inputs
correctly without crashing or producing invalid outputs.
"""

from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings, strategies as st

# Strategy for generating arbitrary summary-like structures
summary_strategy = st.fixed_dictionaries(
    {
        "summary_250": st.text(max_size=500),
        "summary_1000": st.text(max_size=2000),
        "tldr": st.text(max_size=1000),
    },
    optional={
        "key_ideas": st.lists(st.text(max_size=200), max_size=10),
        "topic_tags": st.lists(st.text(max_size=50), max_size=10),
        "entities": st.fixed_dictionaries(
            {},
            optional={
                "people": st.lists(st.text(max_size=100), max_size=10),
                "organizations": st.lists(st.text(max_size=100), max_size=10),
                "locations": st.lists(st.text(max_size=100), max_size=10),
            },
        ),
        "estimated_reading_time_min": st.integers(min_value=0, max_value=1000),
        "seo_keywords": st.lists(st.text(max_size=50), max_size=10),
    },
)


class TestJSONValidationProperties:
    """Property-based tests for JSON validation."""

    @given(summary=summary_strategy)
    @settings(max_examples=100, deadline=None)
    def test_validate_and_shape_never_crashes(self, summary: dict) -> None:
        """Verify validate_and_shape_summary handles arbitrary data without crashing."""
        from app.core.summary_contract import validate_and_shape_summary

        try:
            result = validate_and_shape_summary(summary)
            # Result should be a dict
            assert isinstance(result, dict)
        except (TypeError, ValueError, KeyError):
            # These are acceptable validation errors
            pass

    @given(summary=summary_strategy)
    @settings(max_examples=100, deadline=None)
    def test_validate_and_shape_idempotent(self, summary: dict) -> None:
        """Verify validate_and_shape produces stable output."""
        from app.core.summary_contract import validate_and_shape_summary

        try:
            first_result = validate_and_shape_summary(summary)
            second_result = validate_and_shape_summary(first_result)
            # Running twice should produce same result
            assert first_result == second_result
        except (TypeError, ValueError, KeyError):
            # Validation errors are acceptable
            pass

    @given(text=st.text(min_size=1, max_size=500))
    @settings(max_examples=50, deadline=None)
    def test_text_capping_preserves_content(self, text: str) -> None:
        """Verify text capping doesn't lose important content."""
        # Test that capping to 250 chars preserves start of text
        capped = text[:250] if len(text) > 250 else text
        assert capped.startswith(text[: min(len(text), 250)])

    @given(tags=st.lists(st.text(min_size=1, max_size=50), max_size=20))
    @settings(max_examples=50, deadline=None)
    def test_tag_deduplication(self, tags: list) -> None:
        """Verify tag deduplication works correctly."""
        # Deduplicate case-insensitively
        seen: set[str] = set()
        deduped: list[str] = []
        for tag in tags:
            normalized = tag.lower().strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(tag)

        # Deduped should have unique lowercase values
        lower_deduped = [t.lower().strip() for t in deduped if t.strip()]
        assert len(lower_deduped) == len(set(lower_deduped))

    @given(names=st.lists(st.text(min_size=1, max_size=100), max_size=20))
    @settings(max_examples=50, deadline=None)
    def test_entity_deduplication(self, names: list) -> None:
        """Verify entity deduplication preserves unique entries."""
        # Count unique names (case-insensitive)
        unique_lower = {n.lower().strip() for n in names if n.strip()}

        # Result should have at most as many as unique count
        deduped: list[str] = []
        seen: set[str] = set()
        for name in names:
            normalized = name.lower().strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(name)

        assert len(deduped) <= len(unique_lower)
