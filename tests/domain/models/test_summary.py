"""Unit tests for Summary domain model."""


import pytest

from app.domain.models.summary import Summary


class TestSummary:
    """Test suite for Summary domain model."""

    def test_create_summary(self):
        """Test creating a summary with valid data."""
        summary = Summary(
            request_id=1,
            content={
                "tldr": "Test summary",
                "summary_250": "Brief summary",
                "key_ideas": ["Idea 1", "Idea 2"],
            },
            language="en",
        )

        assert summary.request_id == 1
        assert summary.language == "en"
        assert summary.is_read is False
        assert summary.version == 1

    def test_mark_as_read(self):
        """Test marking summary as read."""
        summary = Summary(
            request_id=1,
            content={"tldr": "Test", "summary_250": "Test", "key_ideas": []},
            language="en",
            is_read=False,
        )

        summary.mark_as_read()

        assert summary.is_read is True

    def test_mark_as_read_when_already_read_raises_error(self):
        """Test that marking already-read summary raises error."""
        summary = Summary(
            request_id=1,
            content={"tldr": "Test", "summary_250": "Test", "key_ideas": []},
            language="en",
            is_read=True,
        )

        with pytest.raises(ValueError, match="already marked as read"):
            summary.mark_as_read()

    def test_mark_as_unread(self):
        """Test marking summary as unread."""
        summary = Summary(
            request_id=1,
            content={"tldr": "Test", "summary_250": "Test", "key_ideas": []},
            language="en",
            is_read=True,
        )

        summary.mark_as_unread()

        assert summary.is_read is False

    def test_mark_as_unread_when_already_unread_raises_error(self):
        """Test that marking already-unread summary raises error."""
        summary = Summary(
            request_id=1,
            content={"tldr": "Test", "summary_250": "Test", "key_ideas": []},
            language="en",
            is_read=False,
        )

        with pytest.raises(ValueError, match="already marked as unread"):
            summary.mark_as_unread()

    def test_validate_content_with_valid_data(self):
        """Test content validation with valid data."""
        summary = Summary(
            request_id=1,
            content={
                "tldr": "Test summary",
                "summary_250": "Brief summary",
                "key_ideas": ["Idea 1"],
            },
            language="en",
        )

        assert summary.validate_content() is True

    def test_validate_content_with_missing_fields(self):
        """Test content validation with missing fields."""
        summary = Summary(
            request_id=1,
            content={"tldr": "Test"},  # Missing required fields
            language="en",
        )

        assert summary.validate_content() is False

    def test_has_minimum_content(self):
        """Test checking for minimum content."""
        summary = Summary(
            request_id=1,
            content={"tldr": "Test summary", "summary_250": "", "key_ideas": []},
            language="en",
        )

        assert summary.has_minimum_content() is True

    def test_has_minimum_content_when_empty(self):
        """Test checking for minimum content when all fields empty."""
        summary = Summary(
            request_id=1,
            content={"tldr": "", "summary_250": "", "summary_1000": "", "key_ideas": []},
            language="en",
        )

        assert summary.has_minimum_content() is False

    def test_get_reading_time_minutes(self):
        """Test getting reading time."""
        summary = Summary(
            request_id=1,
            content={
                "tldr": "Test",
                "summary_250": "Test",
                "key_ideas": [],
                "estimated_reading_time_min": 5,
            },
            language="en",
        )

        assert summary.get_reading_time_minutes() == 5

    def test_get_reading_time_minutes_when_missing(self):
        """Test getting reading time when not provided."""
        summary = Summary(
            request_id=1,
            content={"tldr": "Test", "summary_250": "Test", "key_ideas": []},
            language="en",
        )

        assert summary.get_reading_time_minutes() == 0

    def test_get_key_ideas(self):
        """Test getting key ideas."""
        summary = Summary(
            request_id=1,
            content={
                "tldr": "Test",
                "summary_250": "Test",
                "key_ideas": ["Idea 1", "Idea 2", "Idea 3"],
            },
            language="en",
        )

        ideas = summary.get_key_ideas()
        assert len(ideas) == 3
        assert "Idea 1" in ideas

    def test_get_topic_tags(self):
        """Test getting topic tags."""
        summary = Summary(
            request_id=1,
            content={
                "tldr": "Test",
                "summary_250": "Test",
                "key_ideas": [],
                "topic_tags": ["python", "programming"],
            },
            language="en",
        )

        tags = summary.get_topic_tags()
        assert len(tags) == 2
        assert "python" in tags

    def test_has_insights_when_present(self):
        """Test checking for insights when present."""
        summary = Summary(
            request_id=1,
            content={"tldr": "Test", "summary_250": "Test", "key_ideas": []},
            language="en",
            insights={"additional": "data"},
        )

        assert summary.has_insights() is True

    def test_has_insights_when_absent(self):
        """Test checking for insights when absent."""
        summary = Summary(
            request_id=1,
            content={"tldr": "Test", "summary_250": "Test", "key_ideas": []},
            language="en",
            insights=None,
        )

        assert summary.has_insights() is False

    def test_str_representation(self):
        """Test string representation."""
        summary = Summary(
            id=123,
            request_id=456,
            content={"tldr": "Test", "summary_250": "Test", "key_ideas": []},
            language="en",
            is_read=False,
        )

        str_repr = str(summary)
        assert "Summary(id=123" in str_repr
        assert "request_id=456" in str_repr
        assert "unread" in str_repr
