"""Summary domain model.

This module defines the Summary entity, which represents a processed
content summary with its metadata and insights.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Summary:
    """Domain model for content summary.

    Rich domain model that encapsulates summary data and business logic.
    This is framework-agnostic and contains no infrastructure concerns.
    """

    request_id: int
    content: dict[str, Any]
    language: str
    version: int = 1
    is_read: bool = False
    insights: dict[str, Any] | None = None
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def mark_as_read(self) -> None:
        """Mark this summary as read.

        Raises:
            ValueError: If summary is already marked as read.

        """
        if self.is_read:
            msg = "Summary is already marked as read"
            raise ValueError(msg)
        self.is_read = True

    def mark_as_unread(self) -> None:
        """Mark this summary as unread.

        Raises:
            ValueError: If summary is already marked as unread.

        """
        if not self.is_read:
            msg = "Summary is already marked as unread"
            raise ValueError(msg)
        self.is_read = False

    def validate_content(self) -> bool:
        """Validate that summary content has required fields.

        Returns:
            True if content has all required fields with non-empty values.

        """
        required_fields = ["tldr", "summary_250", "key_ideas"]
        return all(
            field in self.content
            and self.content[field]
            and (not isinstance(self.content[field], str) or self.content[field].strip())
            for field in required_fields
        )

    def has_insights(self) -> bool:
        """Check if summary has insights data.

        Returns:
            True if insights exist and are not empty.

        """
        return self.insights is not None and bool(self.insights)

    def get_reading_time_minutes(self) -> int:
        """Get estimated reading time in minutes.

        Returns:
            Estimated reading time, or 0 if not available.

        """
        return self.content.get("estimated_reading_time_min", 0)

    def get_tldr(self) -> str:
        """Get the TL;DR summary.

        Returns:
            TL;DR text, or empty string if not available.

        """
        return self.content.get("tldr", "")

    def get_summary_250(self) -> str:
        """Get the 250-character summary.

        Returns:
            Summary text, or empty string if not available.

        """
        return self.content.get("summary_250", "")

    def get_summary_1000(self) -> str:
        """Get the 1000-character summary.

        Returns:
            Summary text, or empty string if not available.

        """
        return self.content.get("summary_1000", "")

    def get_key_ideas(self) -> list[str]:
        """Get key ideas from the summary.

        Returns:
            List of key ideas, or empty list if not available.

        """
        key_ideas = self.content.get("key_ideas", [])
        return key_ideas if isinstance(key_ideas, list) else []

    def get_topic_tags(self) -> list[str]:
        """Get topic tags from the summary.

        Returns:
            List of topic tags, or empty list if not available.

        """
        tags = self.content.get("topic_tags", [])
        return tags if isinstance(tags, list) else []

    def get_entities(self) -> list[dict[str, str]]:
        """Get named entities from the summary.

        Returns:
            List of entity dictionaries, or empty list if not available.

        """
        entities = self.content.get("entities", [])
        return entities if isinstance(entities, list) else []

    def get_seo_keywords(self) -> list[str]:
        """Get SEO keywords from the summary.

        Returns:
            List of SEO keywords, or empty list if not available.

        """
        keywords = self.content.get("seo_keywords", [])
        return keywords if isinstance(keywords, list) else []

    def has_minimum_content(self) -> bool:
        """Check if summary has at least one filled summary field.

        Returns:
            True if at least one summary field (tldr, summary_250, or summary_1000) exists.

        """
        return bool(self.get_tldr() or self.get_summary_250() or self.get_summary_1000())

    def get_content_length(self) -> int:
        """Get total character count across all summary fields.

        Returns:
            Total character count.

        """
        return len(self.get_tldr()) + len(self.get_summary_250()) + len(self.get_summary_1000())

    def __str__(self) -> str:
        """String representation of the summary."""
        status = "read" if self.is_read else "unread"
        return (
            f"Summary(id={self.id}, request_id={self.request_id}, lang={self.language}, {status})"
        )

    def __repr__(self) -> str:
        """Detailed representation of the summary."""
        return (
            f"Summary(id={self.id}, request_id={self.request_id}, "
            f"lang={self.language}, version={self.version}, "
            f"is_read={self.is_read}, has_insights={self.has_insights()})"
        )
