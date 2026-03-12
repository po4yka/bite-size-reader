from __future__ import annotations

from typing import Any, cast

import pytest

from app.domain.exceptions.domain_exceptions import ValidationError
from app.domain.models.summary import Summary
from app.domain.services.summary_validator import SummaryValidator


def _summary(
    *,
    request_id: int = 1,
    content: dict[str, Any] | None = None,
    language: str = "en",
    is_read: bool = False,
    **overrides: Any,
) -> Summary:
    summary_content: dict[str, Any] = {
        "tldr": "Short summary",
        "summary_250": "Longer summary",
        "summary_1000": "Detailed summary",
        "key_ideas": ["idea"],
    }
    if content is not None:
        summary_content.update(content)
    return Summary(
        request_id=request_id,
        content=summary_content,
        language=language,
        is_read=is_read,
        **cast("Any", overrides),
    )


def test_validate_content_structure_rejects_non_mapping_and_missing_fields() -> None:
    with pytest.raises(ValidationError, match="dictionary"):
        SummaryValidator.validate_content_structure("bad")  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="missing required fields"):
        SummaryValidator.validate_content_structure({"tldr": "only one field"})


def test_validate_content_quality_requires_summary_text_and_key_ideas() -> None:
    with pytest.raises(ValidationError, match="non-empty summary field"):
        SummaryValidator.validate_content_quality(
            {
                "tldr": " ",
                "summary_250": "",
                "summary_1000": "",
                "key_ideas": ["idea"],
            }
        )

    with pytest.raises(ValidationError, match="at least one key idea"):
        SummaryValidator.validate_content_quality(
            {
                "tldr": "TLDR",
                "summary_250": "",
                "summary_1000": "",
                "key_ideas": [],
            }
        )


def test_validate_language_rejects_invalid_values() -> None:
    with pytest.raises(ValidationError, match="non-empty string"):
        SummaryValidator.validate_language("")

    with pytest.raises(ValidationError, match="whitespace"):
        SummaryValidator.validate_language("   ")

    with pytest.raises(ValidationError, match="too long"):
        SummaryValidator.validate_language("abcdefghijkl")

    SummaryValidator.validate_language("en")


def test_validate_summary_checks_language_content_and_request_id() -> None:
    with pytest.raises(ValidationError, match="valid request_id"):
        SummaryValidator.validate_summary(_summary(request_id=0))

    SummaryValidator.validate_summary(_summary())


def test_can_mark_as_read_and_unread_report_state_transitions() -> None:
    can_mark, reason = SummaryValidator.can_mark_as_read(_summary())
    assert (can_mark, reason) == (True, None)

    already_read, read_reason = SummaryValidator.can_mark_as_read(_summary(is_read=True))
    assert already_read is False
    assert "already marked as read" in read_reason

    missing_content, missing_reason = SummaryValidator.can_mark_as_read(
        _summary(content={"tldr": "", "summary_250": "", "summary_1000": "", "key_ideas": ["idea"]})
    )
    assert missing_content is False
    assert "insufficient content" in missing_reason

    can_unread, unread_reason = SummaryValidator.can_mark_as_unread(_summary(is_read=True))
    assert (can_unread, unread_reason) == (True, None)

    already_unread, already_unread_reason = SummaryValidator.can_mark_as_unread(_summary())
    assert already_unread is False
    assert "already marked as unread" in already_unread_reason
