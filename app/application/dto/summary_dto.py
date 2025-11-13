"""Data Transfer Objects for summary-related operations.

DTOs are simple data structures used to transfer data between layers.
They are framework-agnostic and have no business logic.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class SummaryContentDTO:
    """DTO for summary content data."""

    tldr: str
    summary_250: str
    summary_1000: str | None = None
    key_ideas: list[str] | None = None
    topic_tags: list[str] | None = None
    entities: list[dict[str, str]] | None = None
    seo_keywords: list[str] | None = None
    estimated_reading_time_min: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert DTO to dictionary.

        Returns:
            Dictionary representation of the DTO.
        """
        result: dict[str, Any] = {
            "tldr": self.tldr,
            "summary_250": self.summary_250,
        }

        if self.summary_1000 is not None:
            result["summary_1000"] = self.summary_1000
        if self.key_ideas is not None:
            result["key_ideas"] = self.key_ideas
        if self.topic_tags is not None:
            result["topic_tags"] = self.topic_tags
        if self.entities is not None:
            result["entities"] = self.entities
        if self.seo_keywords is not None:
            result["seo_keywords"] = self.seo_keywords
        if self.estimated_reading_time_min is not None:
            result["estimated_reading_time_min"] = self.estimated_reading_time_min

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SummaryContentDTO":
        """Create DTO from dictionary.

        Args:
            data: Dictionary with summary content data.

        Returns:
            SummaryContentDTO instance.
        """
        return cls(
            tldr=data.get("tldr", ""),
            summary_250=data.get("summary_250", ""),
            summary_1000=data.get("summary_1000"),
            key_ideas=data.get("key_ideas"),
            topic_tags=data.get("topic_tags"),
            entities=data.get("entities"),
            seo_keywords=data.get("seo_keywords"),
            estimated_reading_time_min=data.get("estimated_reading_time_min"),
        )


@dataclass
class SummaryDTO:
    """DTO for summary data transfer between layers."""

    request_id: int
    language: str
    content: dict[str, Any]
    is_read: bool = False
    insights: dict[str, Any] | None = None
    version: int = 1
    summary_id: int | None = None

    @classmethod
    def from_domain_model(cls, summary: Any) -> "SummaryDTO":
        """Create DTO from domain model.

        Args:
            summary: Domain Summary model.

        Returns:
            SummaryDTO instance.
        """
        return cls(
            summary_id=summary.id,
            request_id=summary.request_id,
            language=summary.language,
            content=summary.content,
            is_read=summary.is_read,
            insights=summary.insights,
            version=summary.version,
        )

    def to_domain_model(self) -> Any:
        """Convert DTO to domain model.

        Returns:
            Domain Summary model.
        """
        from app.domain.models.summary import Summary

        return Summary(
            id=self.summary_id,
            request_id=self.request_id,
            language=self.language,
            content=self.content,
            is_read=self.is_read,
            insights=self.insights,
            version=self.version,
        )
