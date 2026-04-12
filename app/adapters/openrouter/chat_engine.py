from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from app.adapter_models.llm.llm_models import LLMCallResult
from app.adapters.openrouter.chat_attempt_runner import ChatAttemptRunner
from app.adapters.openrouter.chat_context_builder import ChatContextBuilder
from app.adapters.openrouter.chat_models import OpenRouterChatClient, StructuredOutputState
from app.adapters.openrouter.chat_response_handler import ChatResponseHandler
from app.adapters.openrouter.chat_streaming import ChatStreamingHandler
from app.adapters.openrouter.chat_transport import ChatTransport
from app.core.async_utils import raise_if_cancelled
from app.core.call_status import CallStatus
from app.core.logging_utils import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def _noop_timeout() -> AsyncIterator[None]:
    """No-op async context manager used when per_model_timeout_sec is None."""
    yield


class OpenRouterChatEngine:
    def __init__(self, client: OpenRouterChatClient) -> None:
        self._client = client
        self._context_builder = ChatContextBuilder(client)
        self._response_handler = ChatResponseHandler(client)
        self._streaming_handler = ChatStreamingHandler(self._response_handler)
        self._transport = ChatTransport(client, self._response_handler, self._streaming_handler)
        self._attempt_runner = ChatAttemptRunner(client, self._transport)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stream: bool = False,
        request_id: int | None = None,
        response_format: dict[str, Any] | None = None,
        model_override: str | None = None,
        fallback_models_override: tuple[str, ...] | list[str] | None = None,
        on_stream_delta: Any | None = None,
        per_model_timeout_sec: float | None = None,
    ) -> LLMCallResult:
        if self._client._closed:
            msg = "Client has been closed"
            raise RuntimeError(msg)

        if self._client._circuit_breaker and not self._client._circuit_breaker.can_proceed():
            return self._circuit_breaker_open_result(request_id)

        context = self._context_builder.prepare(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stream=stream,
            request_id=request_id,
            response_format=response_format,
            model_override=model_override,
            fallback_models_override=fallback_models_override,
        )

        current_request = context.request
        structured_output_state = StructuredOutputState()
        last_error_text: str | None = None
        last_data: dict[str, Any] | None = None
        last_latency: int | None = None
        last_model_reported: str | None = None
        last_response_text: str | None = None
        last_error_context: dict[str, Any] | None = None

        try:
            async with self._client._request_context() as http_client:
                for model_index, model in enumerate(context.models_to_try):
                    try:
                        model_timeout_cm = (
                            asyncio.timeout(per_model_timeout_sec)
                            if per_model_timeout_sec is not None
                            else _noop_timeout()
                        )
                        async with model_timeout_cm:
                            (
                                skip_model,
                                structured_output_state,
                            ) = await self._context_builder.maybe_skip_unsupported_structured_model(
                                model=model,
                                primary_model=context.primary_model,
                                response_format=response_format,
                                request_id=request_id,
                                structured_output_state=structured_output_state,
                            )
                            if skip_model:
                                continue

                            model_state = await self._attempt_runner.run_attempts_for_model(
                                client=http_client,
                                model=model,
                                request=current_request,
                                sanitized_messages=context.sanitized_messages,
                                message_lengths=context.message_lengths,
                                message_roles=context.message_roles,
                                total_chars=context.total_chars,
                                request_id=request_id,
                                initial_rf_mode=context.initial_rf_mode,
                                response_format_initial=context.response_format_initial,
                                structured_output_state=structured_output_state,
                                on_stream_delta=on_stream_delta,
                            )
                    except TimeoutError:
                        last_model_reported = model
                        last_error_text = f"Model {model} timed out after {per_model_timeout_sec}s"
                        last_error_context = {
                            "status_code": None,
                            "message": "Per-model timeout",
                            "timeout": True,
                            "model": model,
                            "timeout_sec": per_model_timeout_sec,
                        }
                        logger.warning(
                            "per_model_timeout",
                            extra={
                                "model": model,
                                "request_id": request_id,
                                "timeout_sec": per_model_timeout_sec,
                                "models_remaining": len(context.models_to_try) - model_index - 1,
                            },
                        )
                        if model_index < len(context.models_to_try) - 1:
                            self._client.error_handler.log_fallback(
                                model,
                                context.models_to_try[model_index + 1],
                                request_id,
                            )
                        continue

                    current_request = model_state.request
                    structured_output_state = model_state.structured_output_state
                    last_error_text = model_state.last_error_text
                    last_data = model_state.last_data
                    last_latency = model_state.last_latency
                    last_model_reported = model_state.last_model_reported
                    last_response_text = model_state.last_response_text
                    last_error_context = model_state.last_error_context

                    if model_state.terminal_result is not None:
                        if self._client._circuit_breaker:
                            if getattr(model_state.terminal_result, "status", None) == "ok":
                                self._client._circuit_breaker.record_success()
                            else:
                                self._client._circuit_breaker.record_failure()
                        return model_state.terminal_result

                    if structured_output_state.parse_error:
                        logger.info(
                            "structured_parse_error_trying_next_model",
                            extra={
                                "model": model,
                                "request_id": request_id,
                                "models_remaining": len(context.models_to_try) - model_index - 1,
                            },
                        )
                    if model_index < len(context.models_to_try) - 1:
                        self._client.error_handler.log_fallback(
                            model,
                            context.models_to_try[model_index + 1],
                            request_id,
                        )
        except Exception as exc:
            raise_if_cancelled(exc)
            last_error_text, last_error_context = self._critical_chat_error_payload(exc)

        self._client.error_handler.log_exhausted(
            context.models_to_try,
            self._client.error_handler._max_retries + 1,
            last_error_text,
            request_id,
        )
        if self._client._circuit_breaker:
            self._client._circuit_breaker.record_failure()
        return self._attempt_runner.build_exhausted_chat_result(
            last_model_reported=last_model_reported,
            last_response_text=last_response_text,
            last_data=last_data,
            last_latency=last_latency,
            last_error_text=last_error_text,
            last_error_context=last_error_context,
            sanitized_messages=context.sanitized_messages,
            structured_output_state=structured_output_state,
        )

    def _circuit_breaker_open_result(self, request_id: int | None) -> LLMCallResult:
        logger.warning(
            "openrouter_circuit_breaker_open",
            extra={
                "request_id": request_id,
                "circuit_state": self._client._circuit_breaker.state.value,
                "failure_count": self._client._circuit_breaker.failure_count,
            },
        )
        return LLMCallResult(
            status=CallStatus.ERROR,
            model=None,
            response_text=None,
            error_text="Service temporarily unavailable (circuit breaker open)",
            tokens_prompt=0,
            tokens_completion=0,
            cost_usd=0.0,
            latency_ms=0,
        )

    def _critical_chat_error_payload(self, error: Exception) -> tuple[str, dict[str, Any]]:
        return (
            f"Critical error: {error!s}",
            {
                "status_code": None,
                "message": "Critical client error",
                "api_error": str(error),
                "error_type": "critical",
            },
        )
