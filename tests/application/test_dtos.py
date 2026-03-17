"""Tests for application-layer DTO classes."""

from __future__ import annotations

from app.application.dto.request_dto import CreateRequestDTO
from app.application.dto.summary_dto import SummaryContentDTO


class TestCreateRequestDTO:
    def test_required_fields_only(self) -> None:
        dto = CreateRequestDTO(user_id=1, chat_id=2, request_type="url")
        assert dto.user_id == 1
        assert dto.chat_id == 2
        assert dto.request_type == "url"
        assert dto.input_url is None

    def test_all_optional_fields(self) -> None:
        dto = CreateRequestDTO(
            user_id=1,
            chat_id=2,
            request_type="forward",
            input_url="https://example.com",
            normalized_url="https://example.com",
            dedupe_hash="abc123",
            correlation_id="cid-1",
            input_message_id=42,
            fwd_from_chat_id=100,
            fwd_from_msg_id=200,
            lang_detected="en",
            content_text="some text",
        )
        assert dto.correlation_id == "cid-1"
        assert dto.lang_detected == "en"


class TestSummaryContentDTO:
    def test_to_dict_includes_required_fields(self) -> None:
        dto = SummaryContentDTO(tldr="short", summary_250="medium")
        result = dto.to_dict()
        assert result["tldr"] == "short"
        assert result["summary_250"] == "medium"

    def test_to_dict_omits_none_optional_fields(self) -> None:
        dto = SummaryContentDTO(tldr="short", summary_250="medium")
        result = dto.to_dict()
        assert "summary_1000" not in result
        assert "key_ideas" not in result

    def test_to_dict_includes_optional_fields_when_set(self) -> None:
        dto = SummaryContentDTO(
            tldr="short",
            summary_250="medium",
            summary_1000="long",
            key_ideas=["idea1"],
            topic_tags=["tech"],
            entities=[{"name": "Python"}],
            seo_keywords=["kw"],
            estimated_reading_time_min=3,
        )
        result = dto.to_dict()
        assert result["summary_1000"] == "long"
        assert result["key_ideas"] == ["idea1"]
        assert result["estimated_reading_time_min"] == 3
