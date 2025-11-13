"""Summary validation domain service.

This service contains business logic for validating summaries according
to domain rules. It is framework-agnostic and has no infrastructure dependencies.
"""

from typing import Any

from app.domain.exceptions.domain_exceptions import ValidationError
from app.domain.models.summary import Summary


class SummaryValidator:
    """Domain service for validating summary content and metadata."""

    @staticmethod
    def validate_content_structure(content: dict[str, Any]) -> None:
        """Validate that content has the required structure.

        Args:
            content: The summary content dictionary to validate.

        Raises:
            ValidationError: If content structure is invalid.
        """
        if not isinstance(content, dict):
            raise ValidationError(
                "Summary content must be a dictionary",
                details={"content_type": str(type(content))},
            )

        required_fields = ["tldr", "summary_250", "key_ideas"]
        missing_fields = [
            field for field in required_fields if field not in content
        ]

        if missing_fields:
            raise ValidationError(
                f"Summary content missing required fields: {', '.join(missing_fields)}",
                details={
                    "missing_fields": missing_fields,
                    "provided_fields": list(content.keys()),
                },
            )

    @staticmethod
    def validate_content_quality(content: dict[str, Any]) -> None:
        """Validate that content has acceptable quality.

        Args:
            content: The summary content dictionary to validate.

        Raises:
            ValidationError: If content quality is insufficient.
        """
        # Check that at least one summary field has content
        tldr = content.get("tldr", "")
        summary_250 = content.get("summary_250", "")
        summary_1000 = content.get("summary_1000", "")

        has_content = any(
            isinstance(field, str) and field.strip()
            for field in [tldr, summary_250, summary_1000]
        )

        if not has_content:
            raise ValidationError(
                "Summary must have at least one non-empty summary field",
                details={"fields_checked": ["tldr", "summary_250", "summary_1000"]},
            )

        # Check that key_ideas is a non-empty list
        key_ideas = content.get("key_ideas", [])
        if not isinstance(key_ideas, list) or not key_ideas:
            raise ValidationError(
                "Summary must have at least one key idea",
                details={"key_ideas": key_ideas},
            )

    @staticmethod
    def validate_language(language: str) -> None:
        """Validate language code.

        Args:
            language: ISO language code to validate.

        Raises:
            ValidationError: If language code is invalid.
        """
        if not language or not isinstance(language, str):
            raise ValidationError(
                "Language must be a non-empty string",
                details={"language": language},
            )

        # Check that it's not just whitespace
        if not language.strip():
            raise ValidationError(
                "Language cannot be empty or whitespace",
                details={"language": language},
            )

        # Check reasonable length (ISO codes are 2-3 characters, but allow up to 10 for variants)
        if len(language.strip()) > 10:
            raise ValidationError(
                "Language code is too long",
                details={"language": language, "length": len(language.strip())},
            )

    @staticmethod
    def validate_summary(summary: Summary) -> None:
        """Validate a complete summary object.

        Args:
            summary: The summary to validate.

        Raises:
            ValidationError: If summary is invalid.
        """
        # Validate language
        SummaryValidator.validate_language(summary.language)

        # Validate content structure
        SummaryValidator.validate_content_structure(summary.content)

        # Validate content quality
        SummaryValidator.validate_content_quality(summary.content)

        # Validate request_id
        if summary.request_id <= 0:
            raise ValidationError(
                "Summary must have a valid request_id",
                details={"request_id": summary.request_id},
            )

    @staticmethod
    def can_mark_as_read(summary: Summary) -> tuple[bool, str | None]:
        """Check if summary can be marked as read.

        Args:
            summary: The summary to check.

        Returns:
            Tuple of (can_mark, reason). If can_mark is False, reason explains why.
        """
        if summary.is_read:
            return False, "Summary is already marked as read"

        if not summary.has_minimum_content():
            return False, "Summary has insufficient content"

        return True, None

    @staticmethod
    def can_mark_as_unread(summary: Summary) -> tuple[bool, str | None]:
        """Check if summary can be marked as unread.

        Args:
            summary: The summary to check.

        Returns:
            Tuple of (can_mark, reason). If can_mark is False, reason explains why.
        """
        if not summary.is_read:
            return False, "Summary is already marked as unread"

        return True, None
