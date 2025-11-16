"""SQLite implementation of request repository.

This adapter translates between domain Request models and database records.
"""

from datetime import UTC, datetime
from typing import Any

from app.domain.models.request import Request, RequestStatus, RequestType


class SqliteRequestRepositoryAdapter:
    """Adapter that wraps the existing Database class for request operations.

    This adapter implements the RequestRepository protocol using the existing
    Database class, providing a bridge between the new domain layer and the
    existing infrastructure.
    """

    def __init__(self, database: Any) -> None:
        """Initialize the repository adapter.

        Args:
            database: The existing Database instance to wrap.

        """
        self._db = database

    async def async_create_request(
        self,
        uid: int,
        cid: int,
        url: str | None = None,
        lang: str | None = None,
        fwd_message_id: int | None = None,
        dedupe_hash: str | None = None,
        correlation_id: str | None = None,
    ) -> int:
        """Create a new request record."""
        return await self._db.async_create_request(
            uid=uid,
            cid=cid,
            url=url,
            lang=lang,
            fwd_message_id=fwd_message_id,
            dedupe_hash=dedupe_hash,
            correlation_id=correlation_id,
        )

    async def async_get_request_by_id(self, request_id: int) -> dict[str, Any] | None:
        """Get a request by its ID."""
        return await self._db.async_get_request_by_id(request_id)

    async def async_get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict[str, Any] | None:
        """Get a request by its deduplication hash."""
        return await self._db.async_get_request_by_dedupe_hash(dedupe_hash)

    async def async_get_request_by_forward(
        self, cid: int, fwd_message_id: int
    ) -> dict[str, Any] | None:
        """Get a request by forwarded message details."""
        return await self._db.async_get_request_by_forward(cid, fwd_message_id)

    async def async_update_request_status(self, request_id: int, status: str) -> None:
        """Update the status of a request."""
        await self._db.async_update_request_status(request_id, status)

    async def async_update_request_correlation_id(
        self, request_id: int, correlation_id: str
    ) -> None:
        """Update the correlation ID of a request."""
        await self._db.async_update_request_correlation_id(request_id, correlation_id)

    async def async_update_request_lang_detected(self, request_id: int, lang: str) -> None:
        """Update the detected language of a request."""
        await self._db.async_update_request_lang_detected(request_id, lang)

    def to_domain_model(self, db_request: dict[str, Any]) -> Request:
        """Convert database record to domain model.

        Args:
            db_request: Dictionary from database query.

        Returns:
            Request domain model.

        """

        # Map database type to domain enum
        request_type_str = db_request.get("type", "unknown")
        try:
            request_type = RequestType(request_type_str)
        except ValueError:
            request_type = RequestType.UNKNOWN

        # Map database status to domain enum
        status_str = db_request.get("status", "pending")
        try:
            status = RequestStatus(status_str)
        except ValueError:
            status = RequestStatus.PENDING

        return Request(
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

    def from_domain_model(self, request: Request) -> dict[str, Any]:
        """Convert domain model to database record format.

        Args:
            request: Request domain model.

        Returns:
            Dictionary suitable for database operations.

        """
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
