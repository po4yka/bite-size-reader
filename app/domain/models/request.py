"""Request domain model.

This module defines the Request entity, which represents a user's request
to process content (URL, forward, etc.).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class RequestType(str, Enum):
    """Types of requests that can be processed."""

    URL = "url"
    FORWARD = "forward"
    TEXT = "text"
    UNKNOWN = "unknown"


class RequestStatus(str, Enum):
    """Status of a request in its lifecycle."""

    PENDING = "pending"
    CRAWLING = "crawling"
    SUMMARIZING = "summarizing"
    COMPLETED = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class Request:
    """Domain model for content processing request.

    Rich domain model that encapsulates request data and business logic.
    This is framework-agnostic and contains no infrastructure concerns.
    """

    user_id: int
    chat_id: int
    request_type: RequestType
    status: RequestStatus = RequestStatus.PENDING
    input_url: str | None = None
    normalized_url: str | None = None
    dedupe_hash: str | None = None
    correlation_id: str | None = None
    input_message_id: int | None = None
    fwd_from_chat_id: int | None = None
    fwd_from_msg_id: int | None = None
    lang_detected: str | None = None
    content_text: str | None = None
    route_version: int = 1
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def mark_as_crawling(self) -> None:
        """Mark request as currently crawling.

        Raises:
            ValueError: If request is not in a valid state for crawling.
        """
        if self.status not in (RequestStatus.PENDING, RequestStatus.ERROR):
            raise ValueError(
                f"Cannot mark request as crawling from status: {self.status}"
            )
        self.status = RequestStatus.CRAWLING

    def mark_as_summarizing(self) -> None:
        """Mark request as currently summarizing.

        Raises:
            ValueError: If request is not in a valid state for summarizing.
        """
        if self.status not in (
            RequestStatus.PENDING,
            RequestStatus.CRAWLING,
            RequestStatus.ERROR,
        ):
            raise ValueError(
                f"Cannot mark request as summarizing from status: {self.status}"
            )
        self.status = RequestStatus.SUMMARIZING

    def mark_as_completed(self) -> None:
        """Mark request as successfully completed.

        Raises:
            ValueError: If request is already completed or cancelled.
        """
        if self.status in (RequestStatus.COMPLETED, RequestStatus.CANCELLED):
            raise ValueError(
                f"Cannot mark request as completed from status: {self.status}"
            )
        self.status = RequestStatus.COMPLETED

    def mark_as_error(self) -> None:
        """Mark request as failed with error.

        Can be called from any status except cancelled.
        """
        if self.status == RequestStatus.CANCELLED:
            raise ValueError("Cannot mark cancelled request as error")
        self.status = RequestStatus.ERROR

    def mark_as_cancelled(self) -> None:
        """Mark request as cancelled by user.

        Raises:
            ValueError: If request is already completed.
        """
        if self.status == RequestStatus.COMPLETED:
            raise ValueError("Cannot cancel completed request")
        self.status = RequestStatus.CANCELLED

    def is_completed(self) -> bool:
        """Check if request completed successfully.

        Returns:
            True if status is COMPLETED.
        """
        return self.status == RequestStatus.COMPLETED

    def is_pending(self) -> bool:
        """Check if request is pending processing.

        Returns:
            True if status is PENDING.
        """
        return self.status == RequestStatus.PENDING

    def is_processing(self) -> bool:
        """Check if request is currently being processed.

        Returns:
            True if status is CRAWLING or SUMMARIZING.
        """
        return self.status in (RequestStatus.CRAWLING, RequestStatus.SUMMARIZING)

    def is_failed(self) -> bool:
        """Check if request failed.

        Returns:
            True if status is ERROR.
        """
        return self.status == RequestStatus.ERROR

    def is_url_request(self) -> bool:
        """Check if this is a URL processing request.

        Returns:
            True if request type is URL.
        """
        return self.request_type == RequestType.URL

    def is_forward_request(self) -> bool:
        """Check if this is a forwarded message request.

        Returns:
            True if request type is FORWARD.
        """
        return self.request_type == RequestType.FORWARD

    def has_url(self) -> bool:
        """Check if request has a URL.

        Returns:
            True if input_url or normalized_url is set.
        """
        return bool(self.input_url or self.normalized_url)

    def get_url(self) -> str | None:
        """Get the URL for this request.

        Returns:
            Normalized URL if available, otherwise input URL.
        """
        return self.normalized_url or self.input_url

    def has_forward_info(self) -> bool:
        """Check if request has forward information.

        Returns:
            True if both forward chat ID and message ID are set.
        """
        return bool(self.fwd_from_chat_id and self.fwd_from_msg_id)

    def set_language(self, language: str) -> None:
        """Set the detected language for this request.

        Args:
            language: ISO language code.

        Raises:
            ValueError: If language is empty.
        """
        if not language or not language.strip():
            raise ValueError("Language cannot be empty")
        self.lang_detected = language.strip()

    def set_correlation_id(self, correlation_id: str) -> None:
        """Set the correlation ID for tracking.

        Args:
            correlation_id: Unique correlation identifier.

        Raises:
            ValueError: If correlation_id is empty.
        """
        if not correlation_id or not correlation_id.strip():
            raise ValueError("Correlation ID cannot be empty")
        self.correlation_id = correlation_id.strip()

    def __str__(self) -> str:
        """String representation of the request."""
        return f"Request(id={self.id}, type={self.request_type.value}, status={self.status.value})"

    def __repr__(self) -> str:
        """Detailed representation of the request."""
        url_info = f", url={self.get_url()[:50]}..." if self.has_url() else ""
        return (
            f"Request(id={self.id}, user_id={self.user_id}, "
            f"type={self.request_type.value}, status={self.status.value}{url_info})"
        )
