"""Domain events for request-related state changes.

Events represent things that have happened in the domain and can be
used to trigger side effects or notify other parts of the system.
"""

from dataclasses import dataclass

from app.domain.events.summary_events import DomainEvent
from app.domain.models.request import RequestStatus


@dataclass(frozen=True)
class RequestCreated(DomainEvent):
    """Event raised when a new request is created."""

    request_id: int
    user_id: int
    chat_id: int
    request_type: str

    def __post_init__(self) -> None:
        """Validate event data."""
        super().__post_init__()
        if self.request_id <= 0:
            raise ValueError("request_id must be positive")
        if self.user_id <= 0:
            raise ValueError("user_id must be positive")


@dataclass(frozen=True)
class RequestStatusChanged(DomainEvent):
    """Event raised when request status changes."""

    request_id: int
    old_status: RequestStatus
    new_status: RequestStatus

    def __post_init__(self) -> None:
        """Validate event data."""
        super().__post_init__()
        if self.request_id <= 0:
            raise ValueError("request_id must be positive")
        if self.old_status == self.new_status:
            raise ValueError("old_status and new_status must be different")


@dataclass(frozen=True)
class RequestCompleted(DomainEvent):
    """Event raised when a request completes successfully."""

    request_id: int
    summary_id: int | None = None

    def __post_init__(self) -> None:
        """Validate event data."""
        super().__post_init__()
        if self.request_id <= 0:
            raise ValueError("request_id must be positive")


@dataclass(frozen=True)
class RequestFailed(DomainEvent):
    """Event raised when a request fails."""

    request_id: int
    error_message: str
    error_details: dict | None = None

    def __post_init__(self) -> None:
        """Validate event data."""
        super().__post_init__()
        if self.request_id <= 0:
            raise ValueError("request_id must be positive")
        if not self.error_message:
            raise ValueError("error_message cannot be empty")


@dataclass(frozen=True)
class RequestCancelled(DomainEvent):
    """Event raised when a request is cancelled."""

    request_id: int
    cancelled_by_user_id: int

    def __post_init__(self) -> None:
        """Validate event data."""
        super().__post_init__()
        if self.request_id <= 0:
            raise ValueError("request_id must be positive")
        if self.cancelled_by_user_id <= 0:
            raise ValueError("cancelled_by_user_id must be positive")
