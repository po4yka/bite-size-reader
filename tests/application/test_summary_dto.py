"""Tests for summary DTOs."""

from __future__ import annotations

from app.application.dto.summary_dto import SummaryContentDTO


def test_summary_content_dto_to_dict_minimal() -> None:
    dto = SummaryContentDTO(tldr="Short summary", summary_250="A short paragraph.")
    d = dto.to_dict()
    assert d == {"tldr": "Short summary", "summary_250": "A short paragraph."}


def test_summary_content_dto_to_dict_all_fields() -> None:
    dto = SummaryContentDTO(
        tldr="tldr",
        summary_250="s250",
        summary_1000="s1000",
        key_ideas=["idea1", "idea2"],
        topic_tags=["tech", "ai"],
        entities=[{"name": "Alice", "type": "person"}],
        seo_keywords=["python", "testing"],
        estimated_reading_time_min=5,
    )
    d = dto.to_dict()
    assert d["summary_1000"] == "s1000"
    assert d["key_ideas"] == ["idea1", "idea2"]
    assert d["topic_tags"] == ["tech", "ai"]
    assert d["estimated_reading_time_min"] == 5


def test_summary_content_dto_from_dict_roundtrip() -> None:
    data = {
        "tldr": "Quick take",
        "summary_250": "Brief text",
        "summary_1000": "Full text",
        "key_ideas": ["idea"],
        "topic_tags": ["tag"],
        "estimated_reading_time_min": 3,
    }
    dto = SummaryContentDTO.from_dict(data)
    assert dto.tldr == "Quick take"
    assert dto.summary_1000 == "Full text"
    assert dto.estimated_reading_time_min == 3
    # Roundtrip
    d = dto.to_dict()
    assert d["tldr"] == data["tldr"]
    assert d["summary_1000"] == data["summary_1000"]


def test_summary_content_dto_omits_none_fields() -> None:
    dto = SummaryContentDTO(tldr="t", summary_250="s")
    d = dto.to_dict()
    assert "summary_1000" not in d
    assert "key_ideas" not in d
    assert "topic_tags" not in d
    assert "entities" not in d
