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
            msg = "occurred_at must be a datetime"
            raise TypeError(msg)


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
            msg = "summary_id must be positive"
            raise ValueError(msg)
        if self.request_id <= 0:
            msg = "request_id must be positive"
            raise ValueError(msg)


@dataclass(frozen=True)
class SummaryMarkedAsRead(DomainEvent):
    """Event raised when a summary is marked as read."""

    summary_id: int

    def __post_init__(self) -> None:
        """Validate event data."""
        super().__post_init__()
        if self.summary_id <= 0:
            msg = "summary_id must be positive"
            raise ValueError(msg)


@dataclass(frozen=True)
class SummaryMarkedAsUnread(DomainEvent):
    """Event raised when a summary is marked as unread."""

    summary_id: int

    def __post_init__(self) -> None:
        """Validate event data."""
        super().__post_init__()
        if self.summary_id <= 0:
            msg = "summary_id must be positive"
            raise ValueError(msg)


@dataclass(frozen=True)
class SummaryInsightsAdded(DomainEvent):
    """Event raised when insights are added to a summary."""

    summary_id: int
    insights: dict[str, Any]

    def __post_init__(self) -> None:
        """Validate event data."""
        super().__post_init__()
        if self.summary_id <= 0:
            msg = "summary_id must be positive"
            raise ValueError(msg)
        if not self.insights:
            msg = "insights cannot be empty"
            raise ValueError(msg)
