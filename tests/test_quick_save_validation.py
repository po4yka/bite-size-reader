"""Tests for QuickSaveRequest Pydantic model validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.models.requests import QuickSaveRequest


class TestQuickSaveValid:
    """Valid QuickSaveRequest instances."""

    def test_all_fields(self) -> None:
        req = QuickSaveRequest(
            url="https://example.com/article",
            title="Great Article",
            selected_text="Key paragraph here.",
            tag_names=["python", "tutorial"],
            summarize=True,
        )
        assert req.url == "https://example.com/article"
        assert req.title == "Great Article"
        assert req.selected_text == "Key paragraph here."
        assert req.tag_names == ["python", "tutorial"]
        assert req.summarize is True

    def test_minimal_fields(self) -> None:
        req = QuickSaveRequest(url="https://example.com")
        assert req.url == "https://example.com"
        assert req.title is None
        assert req.selected_text is None
        assert req.tag_names == []
        assert req.summarize is True

    def test_summarize_false(self) -> None:
        req = QuickSaveRequest(url="https://example.com", summarize=False)
        assert req.summarize is False

    def test_empty_tag_names(self) -> None:
        req = QuickSaveRequest(url="https://example.com", tag_names=[])
        assert req.tag_names == []


class TestQuickSaveInvalid:
    """Invalid QuickSaveRequest instances should raise ValidationError."""

    def test_missing_url(self) -> None:
        with pytest.raises(ValidationError):
            QuickSaveRequest()  # type: ignore[call-arg]

    def test_url_exceeds_max_length(self) -> None:
        with pytest.raises(ValidationError):
            QuickSaveRequest(url="https://example.com/" + "a" * 2048)

    def test_tag_names_wrong_type(self) -> None:
        with pytest.raises(ValidationError):
            QuickSaveRequest(url="https://example.com", tag_names="not-a-list")  # type: ignore[arg-type]


class TestQuickSaveSerialization:
    """Verify serialization round-trips."""

    def test_model_dump(self) -> None:
        req = QuickSaveRequest(
            url="https://example.com",
            tag_names=["ai"],
        )
        data = req.model_dump()
        assert data["url"] == "https://example.com"
        assert data["tag_names"] == ["ai"]
        assert data["summarize"] is True

    def test_model_from_dict(self) -> None:
        raw = {"url": "https://example.com/page", "title": "Page"}
        req = QuickSaveRequest.model_validate(raw)
        assert req.url == "https://example.com/page"
        assert req.title == "Page"
