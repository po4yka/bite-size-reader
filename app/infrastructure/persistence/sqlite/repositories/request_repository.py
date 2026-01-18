"""SQLite implementation of request repository.

This adapter translates between domain Request models and database records.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import peewee

from app.core.time_utils import UTC
from app.db.models import Request, TelegramMessage, model_to_dict
from app.db.utils import prepare_json_payload
from app.domain.models.request import Request as DomainRequest, RequestStatus, RequestType
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteRequestRepositoryAdapter(SqliteBaseRepository):
    """Adapter that implements RequestRepository using Peewee models directly.

    This replaces the legacy delegation to the monolithic Database class.
    """

    async def async_insert_telegram_message(
        self,
        *,
        request_id: int,
        message_id: int | None,
        chat_id: int | None,
        date_ts: int | None,
        text_full: str | None,
        entities_json: Any,
        media_type: str | None,
        media_file_ids_json: Any,
        forward_from_chat_id: int | None,
        forward_from_chat_type: str | None,
        forward_from_chat_title: str | None,
        forward_from_message_id: int | None,
        forward_date_ts: int | None,
        telegram_raw_json: Any,
    ) -> int:
        """Insert a Telegram message snapshot."""

        def _insert() -> int:
            try:
                message = TelegramMessage.create(
                    request=request_id,
                    message_id=message_id,
                    chat_id=chat_id,
                    date_ts=date_ts,
                    text_full=text_full,
                    entities_json=prepare_json_payload(entities_json),
                    media_type=media_type,
                    media_file_ids_json=prepare_json_payload(media_file_ids_json),
                    forward_from_chat_id=forward_from_chat_id,
                    forward_from_chat_type=forward_from_chat_type,
                    forward_from_chat_title=forward_from_chat_title,
                    forward_from_message_id=forward_from_message_id,
                    forward_date_ts=forward_date_ts,
                    telegram_raw_json=prepare_json_payload(telegram_raw_json),
                )
                return message.id
            except peewee.IntegrityError:
                existing = TelegramMessage.get_or_none(TelegramMessage.request == request_id)
                if existing:
                    return existing.id
                raise

        return await self._execute(_insert, operation_name="insert_telegram_message")

    async def async_create_request(
        self,
        *,
        type_: str = "url",
        status: str = "pending",
        correlation_id: str | None = None,
        chat_id: int | None = None,
        user_id: int | None = None,
        input_url: str | None = None,
        normalized_url: str | None = None,
        dedupe_hash: str | None = None,
        input_message_id: int | None = None,
        fwd_from_chat_id: int | None = None,
        fwd_from_msg_id: int | None = None,
        lang_detected: str | None = None,
        content_text: str | None = None,
        route_version: int = 1,
        # Legacy positional support if needed, but kwargs preferred
        uid: int | None = None,
        cid: int | None = None,
        url: str | None = None,
    ) -> int:
        """Create a new request record."""
        # Handle legacy positional args mapped to kwargs
        u_id = user_id or uid
        c_id = chat_id or cid
        i_url = input_url or url

        def _create() -> int:
            try:
                request = Request.create(
                    user_id=u_id,
                    chat_id=c_id,
                    input_url=i_url,
                    normalized_url=normalized_url,
                    lang_detected=lang_detected or lang_detected,
                    input_message_id=input_message_id,
                    fwd_from_chat_id=fwd_from_chat_id,
                    fwd_from_msg_id=fwd_from_msg_id,
                    dedupe_hash=dedupe_hash,
                    correlation_id=correlation_id,
                    type=type_,
                    status=status,
                    content_text=content_text,
                    route_version=route_version,
                )
                return request.id
            except peewee.IntegrityError:
                if dedupe_hash:
                    # Update existing request if it matches dedupe hash
                    Request.update(
                        {
                            Request.correlation_id: correlation_id,
                            Request.status: status,
                            Request.chat_id: c_id,
                            Request.user_id: u_id,
                            Request.input_url: i_url,
                            Request.normalized_url: normalized_url,
                            Request.input_message_id: input_message_id,
                            Request.fwd_from_chat_id: fwd_from_chat_id,
                            Request.fwd_from_msg_id: fwd_from_msg_id,
                            Request.lang_detected: lang_detected,
                            Request.content_text: content_text,
                            Request.route_version: route_version,
                        }
                    ).where(Request.dedupe_hash == dedupe_hash).execute()

                    existing = Request.get_or_none(Request.dedupe_hash == dedupe_hash)
                    if existing:
                        return existing.id
                raise

        return await self._execute(_create, operation_name="create_request")

    async def async_get_request_by_id(self, request_id: int) -> dict[str, Any] | None:
        """Get a request by its ID."""

        def _get() -> dict[str, Any] | None:
            request = Request.get_or_none(Request.id == request_id)
            return model_to_dict(request)

        return await self._execute(_get, operation_name="get_request_by_id", read_only=True)

    async def async_get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict[str, Any] | None:
        """Get a request by its deduplication hash."""

        def _get() -> dict[str, Any] | None:
            request = Request.get_or_none(Request.dedupe_hash == dedupe_hash)
            return model_to_dict(request)

        return await self._execute(
            _get, operation_name="get_request_by_dedupe_hash", read_only=True
        )

    async def async_get_requests_by_ids(
        self, request_ids: list[int], user_id: int | None = None
    ) -> dict[int, dict[str, Any]]:
        """Get multiple requests by IDs, optionally filtered by user.

        Returns:
            Dict mapping request_id to request data.
        """

        def _get() -> dict[int, dict[str, Any]]:
            if not request_ids:
                return {}
            query = Request.select().where(Request.id.in_(request_ids))
            if user_id is not None:
                query = query.where(Request.user_id == user_id)
            return {req.id: model_to_dict(req) or {} for req in query}

        return await self._execute(_get, operation_name="get_requests_by_ids", read_only=True)

    async def async_get_request_by_forward(
        self, cid: int, fwd_message_id: int
    ) -> dict[str, Any] | None:
        """Get a request by forwarded message details."""

        def _get() -> dict[str, Any] | None:
            request = Request.get_or_none(
                (Request.fwd_from_chat_id == cid) & (Request.fwd_from_msg_id == fwd_message_id)
            )
            return model_to_dict(request)

        return await self._execute(_get, operation_name="get_request_by_forward", read_only=True)

    async def async_update_request_status(self, request_id: int, status: str) -> None:
        """Update the status of a request."""

        def _update() -> None:
            Request.update({Request.status: status}).where(Request.id == request_id).execute()

        await self._execute(_update, operation_name="update_request_status")

    async def async_update_request_status_with_correlation(
        self, request_id: int, status: str, correlation_id: str | None
    ) -> None:
        """Update the status and correlation ID of a request."""

        def _update() -> None:
            update_data: dict[Any, Any] = {Request.status: status}
            if correlation_id:
                update_data[Request.correlation_id] = correlation_id
            Request.update(update_data).where(Request.id == request_id).execute()

        await self._execute(_update, operation_name="update_request_status_with_correlation")

    async def async_update_request_correlation_id(
        self, request_id: int, correlation_id: str
    ) -> None:
        """Update the correlation ID of a request."""

        def _update() -> None:
            Request.update({Request.correlation_id: correlation_id}).where(
                Request.id == request_id
            ).execute()

        await self._execute(_update, operation_name="update_request_correlation_id")

    async def async_update_request_lang_detected(self, request_id: int, lang: str) -> None:
        """Update the detected language of a request."""

        def _update() -> None:
            Request.update({Request.lang_detected: lang}).where(Request.id == request_id).execute()

        await self._execute(_update, operation_name="update_request_lang_detected")

    def to_domain_model(self, db_request: dict[str, Any]) -> DomainRequest:
        """Convert database record to domain model."""
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
        """Convert domain model to database record format."""
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

    async def async_get_all_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Get all requests for a user (for sync operations).

        Returns:
            List of request dicts.
        """

        def _get() -> list[dict[str, Any]]:
            requests = Request.select().where(Request.user_id == user_id)
            return [model_to_dict(req) or {} for req in requests]

        return await self._execute(_get, operation_name="get_all_requests_for_user", read_only=True)

    async def async_get_request_id_by_url_with_summary(self, user_id: int, url: str) -> int | None:
        """Get a request ID by URL (input or normalized) that has a summary.

        Args:
            user_id: User ID for authorization
            url: URL to search (matches input_url or normalized_url)

        Returns:
            Request ID if found, None otherwise
        """
        from app.db.models import Summary

        def _get() -> int | None:
            request = (
                Request.select(Request.id)
                .join(Summary)
                .where(
                    (Request.user_id == user_id)
                    & ((Request.input_url == url) | (Request.normalized_url == url))
                    & (Summary.request == Request.id)
                )
                .order_by(Request.created_at.desc())
                .first()
            )
            return request.id if request else None

        return await self._execute(
            _get, operation_name="get_request_id_by_url_with_summary", read_only=True
        )
