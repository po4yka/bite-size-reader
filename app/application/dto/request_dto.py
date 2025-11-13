"""Data Transfer Objects for request-related operations.

DTOs are simple data structures used to transfer data between layers.
They are framework-agnostic and have no business logic.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class CreateRequestDTO:
    """DTO for creating a new request."""

    user_id: int
    chat_id: int
    request_type: str
    input_url: str | None = None
    normalized_url: str | None = None
    dedupe_hash: str | None = None
    correlation_id: str | None = None
    input_message_id: int | None = None
    fwd_from_chat_id: int | None = None
    fwd_from_msg_id: int | None = None
    lang_detected: str | None = None
    content_text: str | None = None

    def to_domain_model(self) -> Any:
        """Convert DTO to domain model.

        Returns:
            Domain Request model.

        """
        from app.domain.models.request import Request, RequestStatus, RequestType

        return Request(
            user_id=self.user_id,
            chat_id=self.chat_id,
            request_type=RequestType(self.request_type),
            status=RequestStatus.PENDING,
            input_url=self.input_url,
            normalized_url=self.normalized_url,
            dedupe_hash=self.dedupe_hash,
            correlation_id=self.correlation_id,
            input_message_id=self.input_message_id,
            fwd_from_chat_id=self.fwd_from_chat_id,
            fwd_from_msg_id=self.fwd_from_msg_id,
            lang_detected=self.lang_detected,
            content_text=self.content_text,
        )


@dataclass
class RequestDTO:
    """DTO for request data transfer between layers."""

    request_id: int
    user_id: int
    chat_id: int
    request_type: str
    status: str
    input_url: str | None = None
    normalized_url: str | None = None
    dedupe_hash: str | None = None
    correlation_id: str | None = None
    lang_detected: str | None = None

    @classmethod
    def from_domain_model(cls, request: Any) -> "RequestDTO":
        """Create DTO from domain model.

        Args:
            request: Domain Request model.

        Returns:
            RequestDTO instance.

        """
        return cls(
            request_id=request.id or 0,
            user_id=request.user_id,
            chat_id=request.chat_id,
            request_type=request.request_type.value,
            status=request.status.value,
            input_url=request.input_url,
            normalized_url=request.normalized_url,
            dedupe_hash=request.dedupe_hash,
            correlation_id=request.correlation_id,
            lang_detected=request.lang_detected,
        )

    def to_domain_model(self) -> Any:
        """Convert DTO to domain model.

        Returns:
            Domain Request model.

        """
        from app.domain.models.request import Request, RequestStatus, RequestType

        return Request(
            id=self.request_id,
            user_id=self.user_id,
            chat_id=self.chat_id,
            request_type=RequestType(self.request_type),
            status=RequestStatus(self.status),
            input_url=self.input_url,
            normalized_url=self.normalized_url,
            dedupe_hash=self.dedupe_hash,
            correlation_id=self.correlation_id,
            lang_detected=self.lang_detected,
        )
