"""Write operations for the SQLite request repository."""

from __future__ import annotations

from typing import Any

import peewee

from app.db.json_utils import prepare_json_payload
from app.db.models import Request
from app.domain.models.request import RequestStatus

from ._repository_mixin_base import SqliteRepositoryMixinBase
from ._request_repo_shared import _utcnow


class RequestRepositoryWriteMixin(SqliteRepositoryMixinBase):
    """Mutating request operations."""

    async def async_create_request(
        self,
        *,
        type_: str = "url",
        status: RequestStatus = RequestStatus.PENDING,
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
    ) -> int:
        """Create a new request record."""

        def _create() -> int:
            try:
                request = Request.create(
                    user_id=user_id,
                    chat_id=chat_id,
                    input_url=input_url,
                    normalized_url=normalized_url,
                    lang_detected=lang_detected,
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
                    Request.update(
                        {
                            Request.correlation_id: correlation_id,
                            Request.status: status,
                            Request.chat_id: chat_id,
                            Request.user_id: user_id,
                            Request.input_url: input_url,
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

    async def async_update_request_content_text(self, request_id: int, content_text: str) -> None:
        """Update the request content text."""

        def _update() -> None:
            Request.update({Request.content_text: content_text}).where(
                Request.id == request_id
            ).execute()

        await self._execute(_update, operation_name="update_request_content_text")

    async def async_update_request_lang_detected(self, request_id: int, lang: str) -> None:
        """Update the detected language of a request."""

        def _update() -> None:
            Request.update({Request.lang_detected: lang}).where(Request.id == request_id).execute()

        await self._execute(_update, operation_name="update_request_lang_detected")

    async def async_update_request_error(
        self,
        request_id: int,
        status: str,
        error_type: str | None = None,
        error_message: str | None = None,
        processing_time_ms: int | None = None,
        error_context_json: Any | None = None,
    ) -> None:
        """Persist structured error details on a request."""

        def _update() -> None:
            update_data: dict[Any, Any] = {
                Request.status: status,
                Request.error_timestamp: _utcnow(),
            }
            if error_type is not None:
                update_data[Request.error_type] = error_type
            if error_message is not None:
                update_data[Request.error_message] = error_message
            if processing_time_ms is not None:
                update_data[Request.processing_time_ms] = processing_time_ms
            if error_context_json is not None:
                update_data[Request.error_context_json] = prepare_json_payload(
                    error_context_json, default={}
                )
            Request.update(update_data).where(Request.id == request_id).execute()

        await self._execute(_update, operation_name="update_request_error")

    async def async_create_minimal_request(
        self,
        *,
        type_: str = "url",
        status: RequestStatus = RequestStatus.PENDING,
        correlation_id: str | None = None,
        chat_id: int | None = None,
        user_id: int | None = None,
        input_url: str | None = None,
        normalized_url: str | None = None,
        dedupe_hash: str | None = None,
    ) -> tuple[int, bool]:
        """Create a minimal request record for pre-batch registration."""

        def _create() -> tuple[int, bool]:
            try:
                request = Request.create(
                    type=type_,
                    status=status,
                    correlation_id=correlation_id,
                    chat_id=chat_id,
                    user_id=user_id,
                    input_url=input_url,
                    normalized_url=normalized_url,
                    dedupe_hash=dedupe_hash,
                )
                return (request.id, True)
            except peewee.IntegrityError:
                if dedupe_hash:
                    existing = Request.get_or_none(Request.dedupe_hash == dedupe_hash)
                    if existing:
                        return (existing.id, False)
                raise

        return await self._execute(_create, operation_name="create_minimal_request")
