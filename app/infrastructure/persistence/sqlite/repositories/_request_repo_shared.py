"""Shared helpers for the SQLite request repository."""

from __future__ import annotations

import datetime as _dt
from datetime import datetime
from typing import Any

from app.core.time_utils import UTC
from app.domain.models.request import Request as DomainRequest, RequestStatus, RequestType


def _utcnow() -> _dt.datetime:
    """Timezone-aware UTC now."""
    return _dt.datetime.now(UTC)


class RequestRepositoryMappingMixin:
    """Domain mapping helpers kept on the public request repository surface."""

    def to_domain_model(self, db_request: dict[str, Any]) -> DomainRequest:
        """Convert a database record to the request domain model."""
        request_type_str = db_request.get("type", "unknown")
        try:
            request_type = RequestType(request_type_str)
        except ValueError:
            request_type = RequestType.UNKNOWN

        status_str = db_request.get("status", "pending")
        try:
            status = RequestStatus(status_str)
        except ValueError:
            status = RequestStatus.PENDING

        return DomainRequest(
            id=db_request.get("id"),
            user_id=db_request["user_id"],
            chat_id=db_request["chat_id"],
            request_type=request_type,
            status=status,
            input_url=db_request.get("input_url"),
            normalized_url=db_request.get("normalized_url"),
            dedupe_hash=db_request.get("dedupe_hash"),
            correlation_id=db_request.get("correlation_id"),
            input_message_id=db_request.get("input_message_id"),
            fwd_from_chat_id=db_request.get("fwd_from_chat_id"),
            fwd_from_msg_id=db_request.get("fwd_from_msg_id"),
            lang_detected=db_request.get("lang_detected"),
            content_text=db_request.get("content_text"),
            route_version=db_request.get("route_version", 1),
            created_at=db_request.get("created_at", datetime.now(UTC)),
        )

    def from_domain_model(self, request: DomainRequest) -> dict[str, Any]:
        """Convert the request domain model to database field values."""
        result: dict[str, Any] = {
            "user_id": request.user_id,
            "chat_id": request.chat_id,
            "type": request.request_type.value,
            "status": request.status.value,
            "route_version": request.route_version,
        }

        if request.id is not None:
            result["id"] = request.id
        if request.input_url is not None:
            result["input_url"] = request.input_url
        if request.normalized_url is not None:
            result["normalized_url"] = request.normalized_url
        if request.dedupe_hash is not None:
            result["dedupe_hash"] = request.dedupe_hash
        if request.correlation_id is not None:
            result["correlation_id"] = request.correlation_id
        if request.input_message_id is not None:
            result["input_message_id"] = request.input_message_id
        if request.fwd_from_chat_id is not None:
            result["fwd_from_chat_id"] = request.fwd_from_chat_id
        if request.fwd_from_msg_id is not None:
            result["fwd_from_msg_id"] = request.fwd_from_msg_id
        if request.lang_detected is not None:
            result["lang_detected"] = request.lang_detected
        if request.content_text is not None:
            result["content_text"] = request.content_text

        return result
