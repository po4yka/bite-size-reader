"""Domain events for summary-related state changes.

Events represent things that have happened in the domain and can be
used to trigger side effects or notify other parts of the system.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events."""

    occurred_at: datetime
    aggregate_id: int | None = None

    def __post_init__(self) -> None:
        """Validate event data after initialization."""
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime")


@dataclass(frozen=True)
class SummaryCreated(DomainEvent):
    """Event raised when a new summary is created."""

    summary_id: int
    request_id: int
    language: str
    has_insights: bool

    def __post_init__(self) -> None:
        """Validate event data."""
        super().__post_init__()
        if self.summary_id <= 0:
            raise ValueError("summary_id must be positive")
        if self.request_id <= 0:
            raise ValueError("request_id must be positive")


@dataclass(frozen=True)
class SummaryMarkedAsRead(DomainEvent):
    """Event raised when a summary is marked as read."""

    summary_id: int

    def __post_init__(self) -> None:
        """Validate event data."""
        super().__post_init__()
        if self.summary_id <= 0:
            raise ValueError("summary_id must be positive")


@dataclass(frozen=True)
class SummaryMarkedAsUnread(DomainEvent):
    """Event raised when a summary is marked as unread."""

    summary_id: int

    def __post_init__(self) -> None:
        """Validate event data."""
        super().__post_init__()
        if self.summary_id <= 0:
            raise ValueError("summary_id must be positive")


@dataclass(frozen=True)
class SummaryInsightsAdded(DomainEvent):
    """Event raised when insights are added to a summary."""

    summary_id: int
    insights: dict[str, Any]

    def __post_init__(self) -> None:
        """Validate event data."""
        super().__post_init__()
        if self.summary_id <= 0:
            raise ValueError("summary_id must be positive")
        if not self.insights:
            raise ValueError("insights cannot be empty")
