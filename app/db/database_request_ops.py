"""Request, crawl, telegram message, and LLM-call operations for Database facade."""
# mypy: disable-error-code=attr-defined

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import peewee

from app.db.models import CrawlResult, LLMCall, Request, TelegramMessage, model_to_dict

JSONValue = Mapping[str, Any] | list[Any] | tuple[Any, ...] | str | None


class DatabaseRequestOpsMixin:
    """Request/crawl/telegram/llm persistence operations."""

    def create_request(
        self,
        *,
        type_: str,
        status: str,
        correlation_id: str | None,
        chat_id: int | None,
        user_id: int | None,
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
                input_message_id=input_message_id,
                fwd_from_chat_id=fwd_from_chat_id,
                fwd_from_msg_id=fwd_from_msg_id,
                lang_detected=lang_detected,
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

    def get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict[str, Any] | None:
        request = Request.get_or_none(Request.dedupe_hash == dedupe_hash)
        return model_to_dict(request)

    async def async_get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict[str, Any] | None:
        """Async wrapper for :meth:`get_request_by_dedupe_hash`."""
        return await self._safe_db_operation(
            self.get_request_by_dedupe_hash,
            dedupe_hash,
            operation_name="get_request_by_dedupe_hash",
            read_only=True,
        )

    def get_request_by_id(self, request_id: int) -> dict[str, Any] | None:
        request = Request.get_or_none(Request.id == request_id)
        return model_to_dict(request)

    async def async_get_request_by_id(self, request_id: int) -> dict[str, Any] | None:
        """Async wrapper for :meth:`get_request_by_id`."""
        return await self._safe_db_operation(
            self.get_request_by_id,
            request_id,
            operation_name="get_request_by_id",
            read_only=True,
        )

    def get_request_by_forward(
        self,
        fwd_chat_id: int,
        fwd_msg_id: int,
    ) -> dict[str, Any] | None:
        request = Request.get_or_none(
            (Request.fwd_from_chat_id == fwd_chat_id) & (Request.fwd_from_msg_id == fwd_msg_id)
        )
        return model_to_dict(request)

    def update_request_status(self, request_id: int, status: str) -> None:
        with self._database.connection_context():
            Request.update({Request.status: status}).where(Request.id == request_id).execute()

    async def async_update_request_status(self, request_id: int, status: str) -> None:
        """Asynchronously update the request status."""
        await self._safe_db_operation(
            self.update_request_status,
            request_id,
            status,
            operation_name="update_request_status",
        )

    def update_request_status_with_correlation(
        self, request_id: int, status: str, correlation_id: str | None
    ) -> None:
        update_map: dict[Any, Any] = {Request.status: status}
        if correlation_id:
            update_map[Request.correlation_id] = correlation_id
        with self._database.connection_context():
            Request.update(update_map).where(Request.id == request_id).execute()

    async def async_update_request_status_with_correlation(
        self, request_id: int, status: str, correlation_id: str | None
    ) -> None:
        """Asynchronously update request status and correlation_id together."""
        await self._safe_db_operation(
            self.update_request_status_with_correlation,
            request_id,
            status,
            correlation_id,
            operation_name="update_request_status_with_correlation",
        )

    def update_request_correlation_id(self, request_id: int, correlation_id: str) -> None:
        with self._database.connection_context():
            Request.update({Request.correlation_id: correlation_id}).where(
                Request.id == request_id
            ).execute()

    def update_request_lang_detected(self, request_id: int, lang: str | None) -> None:
        with self._database.connection_context():
            Request.update({Request.lang_detected: lang}).where(Request.id == request_id).execute()

    def get_crawl_result_by_request(self, request_id: int) -> dict[str, Any] | None:
        result = CrawlResult.get_or_none(CrawlResult.request == request_id)
        data = model_to_dict(result)
        if data:
            self._convert_bool_fields(data, ["firecrawl_success"])
        return data

    async def async_get_crawl_result_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Async wrapper for :meth:`get_crawl_result_by_request`."""
        return await self._safe_db_operation(
            self.get_crawl_result_by_request,
            request_id,
            operation_name="get_crawl_result_by_request",
            read_only=True,
        )

    def insert_crawl_result(
        self,
        *,
        request_id: int,
        source_url: str | None,
        endpoint: str | None,
        http_status: int | None,
        status: str | None,
        options_json: JSONValue,
        correlation_id: str | None,
        content_markdown: str | None,
        content_html: str | None,
        structured_json: JSONValue,
        metadata_json: JSONValue,
        links_json: JSONValue,
        screenshots_paths_json: JSONValue,
        firecrawl_success: bool | None,
        firecrawl_error_code: str | None,
        firecrawl_error_message: str | None,
        firecrawl_details_json: JSONValue,
        raw_response_json: JSONValue,
        latency_ms: int | None,
        error_text: str | None,
    ) -> int:
        try:
            result = CrawlResult.create(
                request=request_id,
                source_url=source_url,
                endpoint=endpoint,
                http_status=http_status,
                status=status,
                options_json=self._prepare_json_payload(options_json, default={}),
                correlation_id=correlation_id,
                content_markdown=content_markdown,
                content_html=content_html,
                structured_json=self._prepare_json_payload(structured_json, default={}),
                metadata_json=self._prepare_json_payload(metadata_json, default={}),
                links_json=self._prepare_json_payload(links_json, default={}),
                screenshots_paths_json=self._prepare_json_payload(screenshots_paths_json),
                firecrawl_success=firecrawl_success,
                firecrawl_error_code=firecrawl_error_code,
                firecrawl_error_message=firecrawl_error_message,
                firecrawl_details_json=self._prepare_json_payload(firecrawl_details_json),
                raw_response_json=self._prepare_json_payload(raw_response_json),
                latency_ms=latency_ms,
                error_text=error_text,
            )
            return result.id
        except peewee.IntegrityError:
            existing = CrawlResult.get_or_none(CrawlResult.request == request_id)
            if existing:
                return existing.id
            raise

    def insert_telegram_message(
        self,
        *,
        request_id: int,
        message_id: int | None,
        chat_id: int | None,
        date_ts: int | None,
        text_full: str | None,
        entities_json: JSONValue,
        media_type: str | None,
        media_file_ids_json: JSONValue,
        forward_from_chat_id: int | None,
        forward_from_chat_type: str | None,
        forward_from_chat_title: str | None,
        forward_from_message_id: int | None,
        forward_date_ts: int | None,
        telegram_raw_json: JSONValue,
    ) -> int:
        try:
            message = TelegramMessage.create(
                request=request_id,
                message_id=message_id,
                chat_id=chat_id,
                date_ts=date_ts,
                text_full=text_full,
                entities_json=self._prepare_json_payload(entities_json),
                media_type=media_type,
                media_file_ids_json=self._prepare_json_payload(media_file_ids_json),
                forward_from_chat_id=forward_from_chat_id,
                forward_from_chat_type=forward_from_chat_type,
                forward_from_chat_title=forward_from_chat_title,
                forward_from_message_id=forward_from_message_id,
                forward_date_ts=forward_date_ts,
                telegram_raw_json=self._prepare_json_payload(telegram_raw_json),
            )
            return message.id
        except peewee.IntegrityError:
            existing = TelegramMessage.get_or_none(TelegramMessage.request == request_id)
            if existing:
                return existing.id
            raise

    def insert_llm_call(
        self,
        *,
        request_id: int | None,
        provider: str | None,
        model: str | None,
        endpoint: str | None,
        request_headers_json: JSONValue,
        request_messages_json: JSONValue,
        response_text: str | None,
        response_json: JSONValue,
        tokens_prompt: int | None,
        tokens_completion: int | None,
        cost_usd: float | None,
        latency_ms: int | None,
        status: str | None,
        error_text: str | None,
        structured_output_used: bool | None,
        structured_output_mode: str | None,
        error_context_json: JSONValue,
    ) -> int:
        headers_payload = self._prepare_json_payload(request_headers_json, default={})
        messages_payload = self._prepare_json_payload(request_messages_json, default=[])
        response_payload = self._prepare_json_payload(response_json, default={})
        error_context_payload = self._prepare_json_payload(error_context_json)
        payload: dict[Any, Any] = {
            LLMCall.request: request_id,
            LLMCall.provider: provider,
            LLMCall.model: model,
            LLMCall.endpoint: endpoint,
            LLMCall.request_headers_json: headers_payload,
            LLMCall.request_messages_json: messages_payload,
            LLMCall.tokens_prompt: tokens_prompt,
            LLMCall.tokens_completion: tokens_completion,
            LLMCall.cost_usd: cost_usd,
            LLMCall.latency_ms: latency_ms,
            LLMCall.status: status,
            LLMCall.error_text: error_text,
            LLMCall.structured_output_used: structured_output_used,
            LLMCall.structured_output_mode: structured_output_mode,
            LLMCall.error_context_json: error_context_payload,
        }
        if provider == "openrouter":
            payload[LLMCall.openrouter_response_text] = response_text
            payload[LLMCall.openrouter_response_json] = response_payload
            payload[LLMCall.response_text] = None
            payload[LLMCall.response_json] = None
        else:
            payload[LLMCall.response_text] = response_text
            payload[LLMCall.response_json] = response_payload

        call = LLMCall.create(**{field.name: value for field, value in payload.items()})
        return call.id

    async def async_insert_llm_call(self, **kwargs: Any) -> int:
        """Persist an LLM call without blocking the event loop."""
        return await self._safe_db_operation(
            self.insert_llm_call,
            operation_name="insert_llm_call",
            **kwargs,
        )

    def get_latest_llm_model_by_request_id(self, request_id: int) -> str | None:
        call = (
            LLMCall.select(LLMCall.model)
            .where(LLMCall.request == request_id, LLMCall.model.is_null(False))
            .order_by(LLMCall.id.desc())
            .first()
        )
        return call.model if call else None
