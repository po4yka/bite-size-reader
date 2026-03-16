from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    import httpx

    from app.adapters.openrouter.error_handler import ErrorHandler
    from app.adapters.openrouter.model_capabilities import ModelCapabilities
    from app.adapters.openrouter.payload_logger import PayloadLogger
    from app.adapters.openrouter.request_builder import RequestBuilder
    from app.adapters.openrouter.response_processor import ResponseProcessor
    from app.models.llm.llm_models import ChatRequest, LLMCallResult


class OpenRouterChatClient(Protocol):
    _closed: bool
    _model: str
    _fallback_models: list[str]
    _enable_structured_outputs: bool
    _max_response_size_bytes: int
    _price_input_per_1k: float | None
    _price_output_per_1k: float | None
    _circuit_breaker: Any | None
    request_builder: RequestBuilder
    response_processor: ResponseProcessor
    model_capabilities: ModelCapabilities
    error_handler: ErrorHandler
    payload_logger: PayloadLogger

    def _get_error_message(self, status_code: int, data: dict[str, Any] | None) -> str: ...

    def _request_context(self) -> AbstractAsyncContextManager[httpx.AsyncClient]: ...


@dataclass
class StructuredOutputState:
    used: bool = False
    mode: str | None = None
    parse_error: bool = False


@dataclass
class PreparedChatContext:
    request: ChatRequest
    sanitized_messages: list[dict[str, Any]]
    message_lengths: list[int]
    message_roles: list[str]
    total_chars: int
    primary_model: str
    models_to_try: list[str]
    response_format_initial: dict[str, Any] | None
    initial_rf_mode: str | None


@dataclass
class AttemptRequestPayload:
    cacheable_messages: list[dict[str, Any]]
    headers: dict[str, str]
    body: dict[str, Any]
    rf_included: bool
    rf_mode_current: str | None
    response_format_current: dict[str, Any] | None
    structured_output_state: StructuredOutputState


@dataclass
class TruncationRecovery:
    original_max_tokens: int
    suggested_max_tokens: int


@dataclass
class RetryDirective:
    rf_mode: str | None
    response_format: dict[str, Any] | None
    backoff_needed: bool
    fallback_to_non_stream: bool = False
    truncation_recovery: TruncationRecovery | None = None


@dataclass
class AttemptOutcome:
    success: bool = False
    llm_result: LLMCallResult | None = None
    error_result: LLMCallResult | None = None
    error_text: str | None = None
    data: dict[str, Any] | None = None
    latency: int | None = None
    model_reported: str | None = None
    response_text: str | None = None
    error_context: dict[str, Any] | None = None
    retry: RetryDirective | None = None
    should_try_next_model: bool = False
    structured_output_state: StructuredOutputState | None = None

    @property
    def should_retry(self) -> bool:
        return self.retry is not None

    @property
    def terminal_result(self) -> LLMCallResult | None:
        if self.llm_result is not None:
            return self.llm_result
        return self.error_result


@dataclass
class ModelRunState:
    request: ChatRequest
    structured_output_state: StructuredOutputState
    terminal_result: LLMCallResult | None = None
    last_error_text: str | None = None
    last_data: dict[str, Any] | None = None
    last_latency: int | None = None
    last_model_reported: str | None = None
    last_response_text: str | None = None
    last_error_context: dict[str, Any] | None = None


@dataclass
class StreamingState:
    model_reported: str
    stream_text_parts: list[str] = field(default_factory=list)
    stream_delta_count: int = 0
    malformed_frames: int = 0
    done_received: bool = False
    first_token_ms: int | None = None
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    native_finish_reason: str | None = None
    last_chunk: dict[str, Any] | None = None
