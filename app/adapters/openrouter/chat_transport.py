from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.adapters.openrouter.chat_models import (
    AttemptOutcome,
    AttemptRequestPayload,
    OpenRouterChatClient,
    RetryDirective,
    StreamingState,
    StructuredOutputState,
)
from app.core.async_utils import raise_if_cancelled
from app.core.http_utils import ResponseSizeError, validate_response_size
from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    import httpx

    from app.adapters.openrouter.chat_response_handler import ChatResponseHandler
    from app.adapters.openrouter.chat_streaming import ChatStreamingHandler
    from app.models.llm.llm_models import ChatRequest

logger = get_logger(__name__)


@dataclass
class RequestBuilderModeOverride:
    request_builder: Any
    mode: str | None
    _original_mode: str | None = None

    def __enter__(self) -> None:
        self._original_mode = getattr(self.request_builder, "_structured_output_mode", None)
        self.request_builder._structured_output_mode = self.mode

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        self.request_builder._structured_output_mode = self._original_mode


class ChatTransport:
    def __init__(
        self,
        client: OpenRouterChatClient,
        response_handler: ChatResponseHandler,
        streaming_handler: ChatStreamingHandler,
    ) -> None:
        self._client = client
        self._response_handler = response_handler
        self._streaming_handler = streaming_handler

    async def attempt_request(
        self,
        client: httpx.AsyncClient,
        *,
        model: str,
        attempt: int,
        sanitized_messages: list[dict[str, Any]],
        request: ChatRequest,
        rf_mode_current: str | None,
        response_format_current: dict[str, Any] | None,
        message_lengths: list[int],
        message_roles: list[str],
        total_chars: int,
        request_id: int | None,
        on_stream_delta: Any | None = None,
    ) -> AttemptOutcome:
        self._client.error_handler.log_attempt(attempt, model, request_id)
        payload = self.build_attempt_request_payload(
            model=model,
            sanitized_messages=sanitized_messages,
            request=request,
            rf_mode_current=rf_mode_current,
            response_format_current=response_format_current,
        )
        started = time.perf_counter()
        try:
            self._log_attempt_request_payload(
                model=model,
                attempt=attempt,
                request_id=request_id,
                message_lengths=message_lengths,
                message_roles=message_roles,
                total_chars=total_chars,
                payload=payload,
            )
            if request.stream:
                return await self._attempt_stream_request(
                    client=client,
                    payload=payload,
                    model=model,
                    request=request,
                    request_id=request_id,
                    attempt=attempt,
                    sanitized_messages=sanitized_messages,
                    on_stream_delta=on_stream_delta,
                    started=started,
                )
            return await self._attempt_non_stream_request(
                client=client,
                payload=payload,
                model=model,
                attempt=attempt,
                request=request,
                request_id=request_id,
                sanitized_messages=sanitized_messages,
                started=started,
            )
        except TimeoutError:
            latency = int((time.perf_counter() - started) * 1000)
            return AttemptOutcome(
                error_text="Request timeout",
                latency=latency,
                model_reported=model,
                error_context={
                    "status_code": None,
                    "message": "Request timeout",
                    "timeout": True,
                },
                should_try_next_model=True,
                structured_output_state=payload.structured_output_state,
            )
        except Exception as exc:
            raise_if_cancelled(exc)
            latency = int((time.perf_counter() - started) * 1000)
            retry = RetryDirective(
                rf_mode=payload.rf_mode_current,
                response_format=payload.response_format_current,
                backoff_needed=attempt < self._client.error_handler._max_retries,
            )
            return AttemptOutcome(
                error_text=str(exc),
                latency=latency,
                retry=retry if attempt < self._client.error_handler._max_retries else None,
                structured_output_state=payload.structured_output_state,
            )

    def build_attempt_request_payload(
        self,
        *,
        model: str,
        sanitized_messages: list[dict[str, Any]],
        request: ChatRequest,
        rf_mode_current: str | None,
        response_format_current: dict[str, Any] | None,
    ) -> AttemptRequestPayload:
        cacheable_messages = self._client.request_builder.build_cacheable_messages(
            sanitized_messages,
            model,
        )
        headers = self._client.request_builder.build_headers()
        with RequestBuilderModeOverride(self._client.request_builder, rf_mode_current):
            body = self._client.request_builder.build_request_body(
                model,
                cacheable_messages,
                request,
                response_format_current,
            )

        if rf_mode_current == "json_object" and "response_format" in body:
            body["response_format"] = {"type": "json_object"}

        should_compress, transform_type = self._client.request_builder.should_apply_compression(
            cacheable_messages,
            model,
        )
        if should_compress and transform_type:
            body["transforms"] = [transform_type]
            total_length = sum(
                self._message_content_length(message) for message in cacheable_messages
            )
            self._client.payload_logger.log_compression_applied(total_length, 200000, model)

        rf_included = "response_format" in body
        structured_output_state = StructuredOutputState(
            used=rf_included,
            mode=rf_mode_current if rf_included else None,
        )
        return AttemptRequestPayload(
            cacheable_messages=cacheable_messages,
            headers=headers,
            body=body,
            rf_included=rf_included,
            rf_mode_current=rf_mode_current,
            response_format_current=response_format_current,
            structured_output_state=structured_output_state,
        )

    async def _attempt_non_stream_request(
        self,
        *,
        client: httpx.AsyncClient,
        payload: AttemptRequestPayload,
        model: str,
        attempt: int,
        request: ChatRequest,
        request_id: int | None,
        sanitized_messages: list[dict[str, Any]],
        started: float,
    ) -> AttemptOutcome:
        resp = await client.post("/chat/completions", headers=payload.headers, json=payload.body)
        try:
            validate_response_size(resp, self._client._max_response_size_bytes, "OpenRouter")
        except ResponseSizeError as size_exc:
            latency = int((time.perf_counter() - started) * 1000)
            return AttemptOutcome(
                error_text=f"Response too large: {size_exc}",
                latency=latency,
                should_try_next_model=True,
                structured_output_state=payload.structured_output_state,
            )

        latency = int((time.perf_counter() - started) * 1000)
        try:
            data = resp.json()
        except Exception as exc:
            raise_if_cancelled(exc)
            return AttemptOutcome(
                error_text=f"Failed to parse JSON response: {exc}",
                latency=latency,
                should_try_next_model=True,
                structured_output_state=payload.structured_output_state,
            )

        if self._client.payload_logger._debug_payloads:
            self._client.payload_logger.log_response_payload(data)

        status_code = resp.status_code
        model_reported = data.get("model", model) if isinstance(data, dict) else model
        if status_code == 200:
            return self._response_handler.handle_successful_response(
                data=data,
                payload=payload,
                model=model,
                model_reported=model_reported,
                latency=latency,
                attempt=attempt,
                request_id=request_id,
                sanitized_messages=sanitized_messages,
                max_tokens=request.max_tokens,
            )
        return await self._response_handler.handle_error_response(
            status_code=status_code,
            data=data,
            resp=resp,
            payload=payload,
            model=model,
            model_reported=model_reported,
            latency=latency,
            attempt=attempt,
            request_id=request_id,
            sanitized_messages=sanitized_messages,
        )

    async def _attempt_stream_request(
        self,
        *,
        client: httpx.AsyncClient,
        payload: AttemptRequestPayload,
        model: str,
        request: ChatRequest,
        request_id: int | None,
        attempt: int,
        sanitized_messages: list[dict[str, Any]],
        on_stream_delta: Any | None,
        started: float,
    ) -> AttemptOutcome:
        state = StreamingState(model_reported=model)
        try:
            stream_ctx = client.stream(
                "POST",
                "/chat/completions",
                headers=payload.headers,
                json=payload.body,
            )
            if hasattr(stream_ctx, "__await__"):
                stream_ctx = await stream_ctx

            async def process_event_payload(raw_payload: str) -> bool:
                return await self._streaming_handler.process_stream_event_payload(
                    payload=raw_payload,
                    state=state,
                    model=model,
                    started=started,
                    on_stream_delta=on_stream_delta,
                    request_id=request_id,
                )

            async with stream_ctx as resp:
                latency = int((time.perf_counter() - started) * 1000)
                status_code = resp.status_code
                if status_code != 200:
                    try:
                        raw_body = await resp.aread()
                        body_text = raw_body.decode("utf-8", errors="replace")
                        data = json.loads(body_text) if body_text else {}
                    except Exception:
                        data = {}
                    outcome = await self._response_handler.handle_error_response(
                        status_code=status_code,
                        data=data if isinstance(data, dict) else {},
                        resp=resp,
                        payload=payload,
                        model=model,
                        model_reported=model,
                        latency=latency,
                        attempt=attempt,
                        request_id=request_id,
                        sanitized_messages=sanitized_messages,
                    )
                    if status_code in {400, 404, 405, 422, 501}:
                        if outcome.retry is not None:
                            # Preserve format downgrade decision, just add stream fallback
                            outcome.retry.fallback_to_non_stream = True
                            outcome.retry.backoff_needed = False
                        else:
                            outcome.retry = RetryDirective(
                                rf_mode=payload.rf_mode_current,
                                response_format=payload.response_format_current,
                                backoff_needed=False,
                                fallback_to_non_stream=True,
                            )
                        outcome.structured_output_state = payload.structured_output_state
                    return outcome

                await self._streaming_handler.consume_stream_sse(
                    resp,
                    process_event_payload=process_event_payload,
                )

            return self._streaming_handler.finalize_stream_success(
                attempt=attempt,
                request_id=request_id,
                model=model,
                request=request,
                payload=payload,
                sanitized_messages=sanitized_messages,
                started=started,
                state=state,
            )
        except Exception as exc:
            raise_if_cancelled(exc)
            latency = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "openrouter_stream_request_failed",
                extra={
                    "request_id": request_id,
                    "model": model,
                    "error": str(exc),
                },
            )
            return AttemptOutcome(
                error_text=f"stream_request_failed: {exc}",
                latency=latency,
                retry=RetryDirective(
                    rf_mode=payload.rf_mode_current,
                    response_format=payload.response_format_current,
                    backoff_needed=False,
                    fallback_to_non_stream=True,
                ),
                structured_output_state=payload.structured_output_state,
            )

    def _log_attempt_request_payload(
        self,
        *,
        model: str,
        attempt: int,
        request_id: int | None,
        message_lengths: list[int],
        message_roles: list[str],
        total_chars: int,
        payload: AttemptRequestPayload,
    ) -> None:
        self._client.payload_logger.log_request(
            model=model,
            attempt=attempt,
            request_id=request_id,
            message_lengths=message_lengths,
            message_roles=message_roles,
            total_chars=total_chars,
            structured_output=payload.rf_included,
            rf_mode=payload.rf_mode_current,
            transforms=payload.body.get("transforms"),
        )
        if self._client.payload_logger._debug_payloads:
            self._client.payload_logger.log_request_payload(
                payload.headers,
                payload.body,
                payload.cacheable_messages,
                payload.rf_mode_current,
            )

    def _message_content_length(self, message: dict[str, Any]) -> int:
        content = message.get("content")
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            return sum(len(part.get("text", "")) for part in content if isinstance(part, dict))
        return 0
