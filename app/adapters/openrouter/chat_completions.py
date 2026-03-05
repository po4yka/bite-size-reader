from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from app.adapters.openrouter.exceptions import ValidationError
from app.core.async_utils import raise_if_cancelled
from app.core.http_utils import ResponseSizeError, validate_response_size
from app.models.llm.llm_models import ChatRequest, LLMCallResult
from app.observability.metrics import record_draft_stream_event, record_stream_latency_ms

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)


def _message_content_length(message: dict[str, Any]) -> int:
    content = message.get("content")
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(part.get("text", "")) for part in content if isinstance(part, dict))
    return 0


def _build_attempt_request_payload(
    self,
    *,
    model: str,
    sanitized_messages: list[dict[str, Any]],
    request: ChatRequest,
    rf_mode_current: str,
    response_format_current: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any], bool, bool, str | None]:
    cacheable_messages = self.request_builder.build_cacheable_messages(sanitized_messages, model)
    self.request_builder._structured_output_mode = rf_mode_current
    headers = self.request_builder.build_headers()
    body = self.request_builder.build_request_body(
        model, cacheable_messages, request, response_format_current
    )
    if rf_mode_current == "json_object" and "response_format" in body:
        body["response_format"] = {"type": "json_object"}

    should_compress, transform_type = self.request_builder.should_apply_compression(
        cacheable_messages, model
    )
    if should_compress and transform_type:
        body["transforms"] = [transform_type]
        total_length = sum(_message_content_length(msg) for msg in cacheable_messages)
        self.payload_logger.log_compression_applied(total_length, 200000, model)

    rf_included = "response_format" in body
    structured_output_used = rf_included
    structured_output_mode_used = rf_mode_current if rf_included else None
    return (
        cacheable_messages,
        headers,
        body,
        rf_included,
        structured_output_used,
        structured_output_mode_used,
    )


def _copy_request_with_max_tokens(request: ChatRequest, max_tokens: int) -> ChatRequest:
    return ChatRequest(
        messages=request.messages,
        temperature=request.temperature,
        max_tokens=max_tokens,
        top_p=request.top_p,
        stream=request.stream,
        request_id=request.request_id,
        response_format=request.response_format,
        model_override=request.model_override,
    )


def _copy_request_with_stream(request: ChatRequest, stream: bool) -> ChatRequest:
    return ChatRequest(
        messages=request.messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        top_p=request.top_p,
        stream=stream,
        request_id=request.request_id,
        response_format=request.response_format,
        model_override=request.model_override,
    )


async def _dispatch_stream_delta(
    on_stream_delta: Any | None,
    delta_text: str,
) -> None:
    if not on_stream_delta or not delta_text:
        return
    callback_result = on_stream_delta(delta_text)
    if hasattr(callback_result, "__await__"):
        await callback_result


def _extract_stream_delta_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""

    delta = first_choice.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            return "".join(parts)

    # Some providers may emit text as message.content in final chunk.
    message = first_choice.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    return ""


async def _run_attempts_for_model(
    self,
    *,
    client: httpx.AsyncClient,
    model: str,
    request: ChatRequest,
    sanitized_messages: list[dict[str, Any]],
    message_lengths: list[int],
    message_roles: list[str],
    total_chars: int,
    request_id: int | None,
    builder_rf_mode_original: str,
    response_format_initial: dict[str, Any] | None,
    structured_output_used: bool,
    structured_output_mode_used: str | None,
    on_stream_delta: Any | None = None,
) -> dict[str, Any]:
    rf_mode_current = builder_rf_mode_original
    response_format_current = response_format_initial
    truncation_count = 0
    state: dict[str, Any] = {
        "terminal_result": None,
        "request": request,
        "last_error_text": None,
        "last_data": None,
        "last_latency": None,
        "last_model_reported": None,
        "last_response_text": None,
        "last_error_context": None,
        "structured_parse_error": False,
        "structured_output_used": structured_output_used,
        "structured_output_mode_used": structured_output_mode_used,
    }

    for attempt in range(self.error_handler._max_retries + 1):
        try:
            result = await self._attempt_request(
                client=client,
                model=model,
                attempt=attempt,
                sanitized_messages=sanitized_messages,
                request=state["request"],
                rf_mode_current=rf_mode_current,
                response_format_current=response_format_current,
                message_lengths=message_lengths,
                message_roles=message_roles,
                total_chars=total_chars,
                request_id=request_id,
                on_stream_delta=on_stream_delta,
            )
        except Exception as e:
            raise_if_cancelled(e)
            state["last_error_text"] = f"Unexpected error: {e!s}"
            state["last_error_context"] = {
                "status_code": None,
                "message": "Client exception",
                "api_error": str(e),
            }
            if attempt < self.error_handler._max_retries:
                await self.error_handler.sleep_backoff(attempt)
                continue
            break

        if result.get("success"):
            state["terminal_result"] = result["llm_result"]
            return state

        if result.get("should_retry"):
            if result.get("fallback_to_non_stream") and state["request"].stream:
                logger.warning(
                    "openrouter_stream_fallback_non_stream",
                    extra={
                        "model": model,
                        "attempt": attempt + 1,
                        "request_id": request_id,
                    },
                )
                state["request"] = _copy_request_with_stream(state["request"], False)
                continue

            rf_mode_current = result.get("new_rf_mode", rf_mode_current)
            response_format_current = result.get("new_response_format", response_format_current)
            state["structured_output_used"] = result.get(
                "structured_output_used", state["structured_output_used"]
            )
            state["structured_output_mode_used"] = result.get(
                "structured_output_mode_used", state["structured_output_mode_used"]
            )

            truncation_recovery = result.get("truncation_recovery")
            if truncation_recovery:
                truncation_count += 1
                if truncation_count >= 2:
                    logger.warning(
                        "truncation_limit_reached",
                        extra={"model": model, "count": truncation_count, "request_id": request_id},
                    )
                    state["last_error_text"] = "repeated_truncation"
                    state["last_error_context"] = {
                        "status_code": None,
                        "message": "Repeated truncation - trying next model",
                        "truncation_count": truncation_count,
                    }
                    break
                new_max = truncation_recovery.get("suggested_max_tokens")
                if new_max and (
                    not state["request"].max_tokens or new_max > state["request"].max_tokens
                ):
                    logger.info(
                        "truncation_recovery_increasing_max_tokens",
                        extra={
                            "model": model,
                            "original_max": state["request"].max_tokens,
                            "new_max": new_max,
                            "attempt": attempt + 1,
                            "truncation_count": truncation_count,
                        },
                    )
                    state["request"] = _copy_request_with_max_tokens(state["request"], new_max)

            if result.get("backoff_needed"):
                await self.error_handler.sleep_backoff(attempt)
            continue

        state["last_error_text"] = result.get("error_text")
        state["last_data"] = result.get("data")
        state["last_latency"] = result.get("latency")
        state["last_model_reported"] = result.get("model_reported")
        state["last_response_text"] = result.get("response_text")
        state["last_error_context"] = result.get("error_context")
        state["structured_parse_error"] = result.get("structured_parse_error", False)
        if result.get("error_result"):
            state["terminal_result"] = result["error_result"]
            return state
        if result.get("should_try_next_model"):
            break

    return state


def _build_exhausted_chat_result(
    self,
    *,
    last_model_reported: str | None,
    last_response_text: str | None,
    last_data: dict[str, Any] | None,
    last_latency: int | None,
    structured_parse_error: bool,
    last_error_text: str | None,
    sanitized_messages: list[dict[str, Any]],
    structured_output_used: bool,
    structured_output_mode_used: str | None,
    last_error_context: dict[str, Any] | None,
) -> LLMCallResult:
    redacted_headers = self.request_builder.get_redacted_headers(
        {"Authorization": "REDACTED", "Content-Type": "application/json"}
    )
    return LLMCallResult(
        status="error",
        model=last_model_reported,
        response_text=last_response_text,
        response_json=last_data,
        openrouter_response_text=last_response_text,
        openrouter_response_json=last_data,
        tokens_prompt=None,
        tokens_completion=None,
        cost_usd=None,
        latency_ms=last_latency,
        error_text=(
            "structured_output_parse_error"
            if structured_parse_error
            else (last_error_text or "All retries and fallbacks exhausted")
        ),
        request_headers=redacted_headers,
        request_messages=sanitized_messages,
        endpoint="/api/v1/chat/completions",
        structured_output_used=structured_output_used,
        structured_output_mode=structured_output_mode_used,
        error_context=last_error_context,
    )


def _prepare_chat_context(
    self,
    *,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int | None,
    top_p: float | None,
    stream: bool,
    request_id: int | None,
    response_format: dict[str, Any] | None,
    model_override: str | None,
    fallback_models_override: tuple[str, ...] | list[str] | None,
) -> tuple[
    ChatRequest,
    list[dict[str, Any]],
    list[int],
    list[str],
    int,
    str,
    list[str],
]:
    if not messages:
        msg = "Messages cannot be empty"
        raise ValidationError(msg, context={"messages_count": 0})
    if not isinstance(messages, list):
        msg = f"Messages must be a list, got {type(messages).__name__}"
        raise ValidationError(msg, context={"messages_type": type(messages).__name__})

    request = ChatRequest(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        stream=stream,
        request_id=request_id,
        response_format=response_format,
        model_override=model_override,
    )
    try:
        self.request_builder.validate_chat_request(request)
        sanitized_messages = self.request_builder.sanitize_messages(messages)
    except Exception as e:
        raise_if_cancelled(e)
        msg = f"Request validation failed: {e}"
        raise ValidationError(
            msg,
            context={"original_error": str(e), "messages_count": len(messages)},
        ) from e

    message_lengths = [len(str(msg.get("content", ""))) for msg in sanitized_messages]
    message_roles = [msg.get("role", "?") for msg in sanitized_messages]
    total_chars = sum(message_lengths)
    primary_model = model_override if model_override else self._model
    fallback_models = (
        list(fallback_models_override) if fallback_models_override else self._fallback_models
    )
    models_to_try = self.model_capabilities.build_model_fallback_list(
        primary_model, fallback_models, response_format, self._enable_structured_outputs
    )
    if not models_to_try:
        msg = "No models available to try"
        raise ValueError(msg)
    return (
        request,
        sanitized_messages,
        message_lengths,
        message_roles,
        total_chars,
        primary_model,
        models_to_try,
    )


async def _maybe_skip_unsupported_structured_model(
    self,
    *,
    model: str,
    primary_model: str,
    response_format: dict[str, Any] | None,
    request_id: int | None,
    structured_output_used: bool,
    structured_output_mode_used: str | None,
) -> tuple[bool, bool, str | None]:
    if not (response_format and self._enable_structured_outputs):
        return False, structured_output_used, structured_output_mode_used
    try:
        await self.model_capabilities.ensure_structured_supported_models()
        if self.model_capabilities.supports_structured_outputs(model):
            return False, structured_output_used, structured_output_mode_used
    except Exception as e:
        raise_if_cancelled(e)
        logger.warning("Failed to check model capabilities: %s", e)
        return False, structured_output_used, structured_output_mode_used

    reason = "no_structured_outputs_primary" if model == primary_model else "no_structured_outputs"
    self.error_handler.log_skip_model(model, reason, request_id)
    if model == primary_model:
        return False, False, None
    return True, structured_output_used, structured_output_mode_used


def _circuit_breaker_open_result(self, request_id: int | None) -> LLMCallResult:
    logger.warning(
        "openrouter_circuit_breaker_open",
        extra={
            "request_id": request_id,
            "circuit_state": self._circuit_breaker.state.value,
            "failure_count": self._circuit_breaker.failure_count,
        },
    )
    return LLMCallResult(
        status="error",
        model=None,
        response_text=None,
        error_text="Service temporarily unavailable (circuit breaker open)",
        tokens_prompt=0,
        tokens_completion=0,
        cost_usd=0.0,
        latency_ms=0,
    )


def _unpack_model_state(model_state: dict[str, Any]) -> tuple[Any, ...]:
    return (
        model_state["request"],
        model_state["structured_output_used"],
        model_state["structured_output_mode_used"],
        model_state["last_error_text"],
        model_state["last_data"],
        model_state["last_latency"],
        model_state["last_model_reported"],
        model_state["last_response_text"],
        model_state["last_error_context"],
        model_state["structured_parse_error"],
    )


def _critical_chat_error_payload(error: Exception) -> tuple[str, dict[str, Any]]:
    return (
        f"Critical error: {error!s}",
        {
            "status_code": None,
            "message": "Critical client error",
            "api_error": str(error),
            "error_type": "critical",
        },
    )


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
) -> LLMCallResult:
    """Enhanced chat method with structured output support."""
    if self._closed:
        msg = "Client has been closed"
        raise RuntimeError(msg)

    if self._circuit_breaker and not self._circuit_breaker.can_proceed():
        return _circuit_breaker_open_result(self, request_id)

    (
        request,
        sanitized_messages,
        message_lengths,
        message_roles,
        total_chars,
        primary_model,
        models_to_try,
    ) = _prepare_chat_context(
        self,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        stream=stream,
        request_id=request_id,
        response_format=response_format,
        model_override=model_override,
        fallback_models_override=fallback_models_override,
    )

    builder_rf_mode_original = self.request_builder._structured_output_mode
    response_format_initial = response_format if isinstance(response_format, dict) else None
    last_error_text: str | None = None
    last_data: dict[str, Any] | None = None
    last_latency: int | None = None
    last_model_reported: str | None = None
    last_response_text: str | None = None
    structured_output_used = False
    structured_output_mode_used: str | None = None
    structured_parse_error = False
    last_error_context: dict[str, Any] | None = None

    try:
        async with self._request_context() as client:
            for model_idx, model in enumerate(models_to_try):
                (
                    skip_model,
                    structured_output_used,
                    structured_output_mode_used,
                ) = await _maybe_skip_unsupported_structured_model(
                    self,
                    model=model,
                    primary_model=primary_model,
                    response_format=response_format,
                    request_id=request_id,
                    structured_output_used=structured_output_used,
                    structured_output_mode_used=structured_output_mode_used,
                )
                if skip_model:
                    continue

                model_state = await _run_attempts_for_model(
                    self,
                    client=client,
                    model=model,
                    request=request,
                    sanitized_messages=sanitized_messages,
                    message_lengths=message_lengths,
                    message_roles=message_roles,
                    total_chars=total_chars,
                    request_id=request_id,
                    builder_rf_mode_original=builder_rf_mode_original,
                    response_format_initial=response_format_initial,
                    structured_output_used=structured_output_used,
                    structured_output_mode_used=structured_output_mode_used,
                    on_stream_delta=on_stream_delta,
                )
                (
                    request,
                    structured_output_used,
                    structured_output_mode_used,
                    last_error_text,
                    last_data,
                    last_latency,
                    last_model_reported,
                    last_response_text,
                    last_error_context,
                    structured_parse_error,
                ) = _unpack_model_state(model_state)

                if model_state["terminal_result"] is not None:
                    terminal_result = model_state["terminal_result"]
                    if self._circuit_breaker:
                        if getattr(terminal_result, "status", None) == "ok":
                            self._circuit_breaker.record_success()
                        else:
                            self._circuit_breaker.record_failure()
                    return terminal_result

                if structured_parse_error:
                    logger.info(
                        "structured_parse_error_trying_next_model",
                        extra={
                            "model": model,
                            "request_id": request_id,
                            "models_remaining": len(models_to_try) - model_idx - 1,
                        },
                    )
                if model_idx < len(models_to_try) - 1:
                    self.error_handler.log_fallback(model, models_to_try[model_idx + 1], request_id)

    except Exception as e:
        raise_if_cancelled(e)
        last_error_text, last_error_context = _critical_chat_error_payload(e)
    finally:
        self.request_builder._structured_output_mode = builder_rf_mode_original

    self.error_handler.log_exhausted(
        models_to_try, self.error_handler._max_retries + 1, last_error_text, request_id
    )
    if self._circuit_breaker:
        self._circuit_breaker.record_failure()
    return _build_exhausted_chat_result(
        self,
        last_model_reported=last_model_reported,
        last_response_text=last_response_text,
        last_data=last_data,
        last_latency=last_latency,
        structured_parse_error=structured_parse_error,
        last_error_text=last_error_text,
        sanitized_messages=sanitized_messages,
        structured_output_used=structured_output_used,
        structured_output_mode_used=structured_output_mode_used,
        last_error_context=last_error_context,
    )


async def _attempt_stream_request(
    self,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    body: dict[str, Any],
    model: str,
    request: ChatRequest,
    request_id: int | None,
    attempt: int,
    rf_included: bool,
    rf_mode_current: str,
    response_format_current: dict[str, Any] | None,
    structured_output_used: bool,
    structured_output_mode_used: str | None,
    sanitized_messages: list[dict[str, Any]],
    on_stream_delta: Any | None,
    started: float,
) -> dict[str, Any]:
    """Attempt streaming OpenRouter request and reconstruct final completion payload."""
    stream_text_parts: list[str] = []
    stream_delta_count = 0
    malformed_frames = 0
    done_received = False
    first_token_ms: int | None = None
    model_reported = model
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    native_finish_reason: str | None = None
    last_chunk: dict[str, Any] | None = None

    async def _process_event_payload(payload: str) -> bool:
        nonlocal done_received
        nonlocal malformed_frames
        nonlocal last_chunk
        nonlocal model_reported
        nonlocal usage
        nonlocal finish_reason
        nonlocal native_finish_reason
        nonlocal first_token_ms
        nonlocal stream_delta_count

        payload = payload.strip()
        if not payload:
            return False
        if payload == "[DONE]":
            done_received = True
            return True

        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            malformed_frames += 1
            return False

        if not isinstance(chunk, dict):
            malformed_frames += 1
            return False

        last_chunk = chunk
        model_reported = chunk.get("model", model_reported)
        usage_chunk = chunk.get("usage")
        if isinstance(usage_chunk, dict):
            usage = usage_chunk

        choices = chunk.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0] if isinstance(choices[0], dict) else {}
            finish_reason = first_choice.get("finish_reason") or finish_reason
            native_finish_reason = first_choice.get("native_finish_reason") or native_finish_reason

        delta_text = _extract_stream_delta_text(chunk)
        if delta_text:
            if first_token_ms is None:
                first_token_ms = int((time.perf_counter() - started) * 1000)
                record_stream_latency_ms("stream_first_token_ms", first_token_ms)
            stream_text_parts.append(delta_text)
            stream_delta_count += 1
            record_draft_stream_event("stream_delta_count")
            try:
                await _dispatch_stream_delta(on_stream_delta, delta_text)
            except Exception as callback_exc:
                raise_if_cancelled(callback_exc)
                logger.warning(
                    "openrouter_stream_delta_callback_failed",
                    extra={"error": str(callback_exc), "request_id": request_id},
                )

        return False

    try:
        # Some mocks expose `stream()` as an awaitable that yields the async
        # context manager, while httpx returns the context manager directly.
        stream_ctx = client.stream("POST", "/chat/completions", headers=headers, json=body)
        if hasattr(stream_ctx, "__await__"):
            stream_ctx = await stream_ctx

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
                model_reported = model
                result = await self._handle_error_response(
                    status_code=status_code,
                    data=data if isinstance(data, dict) else {},
                    resp=resp,
                    rf_included=rf_included,
                    rf_mode_current=rf_mode_current,
                    response_format_current=response_format_current,
                    model=model,
                    model_reported=model_reported,
                    latency=latency,
                    attempt=attempt,
                    request_id=request_id,
                    headers=headers,
                    sanitized_messages=sanitized_messages,
                )
                # Stream endpoints can fail on provider side; degrade to non-stream path.
                if status_code in {400, 404, 405, 422, 501}:
                    result["should_retry"] = True
                    result["backoff_needed"] = False
                    result["fallback_to_non_stream"] = True
                return result

            # Parse SSE frames (`data:` lines grouped by blank separator)
            current_event_data_lines: list[str] = []
            async for line in resp.aiter_lines():
                if line == "":
                    if not current_event_data_lines:
                        continue
                    payload = "\n".join(current_event_data_lines).strip()
                    current_event_data_lines.clear()
                    if await _process_event_payload(payload):
                        break
                    continue

                if line.startswith("data:"):
                    payload_line = line[5:].lstrip()
                    # Some streams omit blank separators between events.
                    # Flush buffered payload whenever a new `data:` line starts.
                    if current_event_data_lines:
                        buffered_payload = "\n".join(current_event_data_lines).strip()
                        if await _process_event_payload(buffered_payload):
                            break
                        current_event_data_lines.clear()
                    current_event_data_lines.append(payload_line)

            if current_event_data_lines and not done_received:
                payload = "\n".join(current_event_data_lines).strip()
                await _process_event_payload(payload)

        completion_ms = int((time.perf_counter() - started) * 1000)
        record_stream_latency_ms("stream_completion_ms", completion_ms)

        full_text = "".join(stream_text_parts)
        if not full_text and isinstance(last_chunk, dict):
            full_text = _extract_stream_delta_text(last_chunk)

        if not full_text:
            return {
                "success": False,
                "error_text": "stream_empty_completion",
                "latency": completion_ms,
                "should_retry": True,
                "fallback_to_non_stream": True,
                "backoff_needed": False,
            }

        if malformed_frames > 0:
            logger.warning(
                "openrouter_stream_malformed_frames",
                extra={
                    "request_id": request_id,
                    "model": model_reported,
                    "malformed_frames": malformed_frames,
                },
            )

        synthesized_data: dict[str, Any] = {
            "id": f"stream_{request_id or 'n/a'}",
            "model": model_reported,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": full_text},
                    "finish_reason": finish_reason or ("stop" if done_received else None),
                    "native_finish_reason": native_finish_reason,
                }
            ],
        }
        if usage is not None:
            synthesized_data["usage"] = usage

        logger.info(
            "openrouter_stream_complete",
            extra={
                "request_id": request_id,
                "model": model_reported,
                "stream_delta_count": stream_delta_count,
                "stream_first_token_ms": first_token_ms,
                "stream_completion_ms": completion_ms,
            },
        )

        return await self._handle_successful_response(
            data=synthesized_data,
            rf_included=rf_included,
            rf_mode_current=rf_mode_current,
            response_format_current=response_format_current,
            model=model,
            model_reported=model_reported,
            latency=completion_ms,
            attempt=attempt,
            request_id=request_id,
            structured_output_used=structured_output_used,
            structured_output_mode_used=structured_output_mode_used,
            headers=headers,
            sanitized_messages=sanitized_messages,
            max_tokens=request.max_tokens,
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
        return {
            "success": False,
            "error_text": f"stream_request_failed: {exc}",
            "latency": latency,
            "should_retry": True,
            "fallback_to_non_stream": True,
            "backoff_needed": False,
        }


async def _attempt_request(
    self,
    client: httpx.AsyncClient,
    model: str,
    attempt: int,
    sanitized_messages: list[dict[str, Any]],
    request: ChatRequest,
    rf_mode_current: str,
    response_format_current: dict[str, Any] | None,
    message_lengths: list[int],
    message_roles: list[str],
    total_chars: int,
    request_id: int | None,
    on_stream_delta: Any | None = None,
) -> dict[str, Any]:
    """Attempt a single request with comprehensive error handling."""
    self.error_handler.log_attempt(attempt, model, request_id)
    (
        cacheable_messages,
        headers,
        body,
        rf_included,
        structured_output_used,
        structured_output_mode_used,
    ) = _build_attempt_request_payload(
        self,
        model=model,
        sanitized_messages=sanitized_messages,
        request=request,
        rf_mode_current=rf_mode_current,
        response_format_current=response_format_current,
    )
    started = time.perf_counter()
    try:
        self.payload_logger.log_request(
            model=model,
            attempt=attempt,
            request_id=request_id,
            message_lengths=message_lengths,
            message_roles=message_roles,
            total_chars=total_chars,
            structured_output=rf_included,
            rf_mode=rf_mode_current,
            transforms=body.get("transforms"),
        )

        if self.payload_logger._debug_payloads:
            self.payload_logger.log_request_payload(
                headers, body, cacheable_messages, rf_mode_current
            )

        if request.stream:
            return await _attempt_stream_request(
                self,
                client=client,
                headers=headers,
                body=body,
                model=model,
                request=request,
                request_id=request_id,
                attempt=attempt,
                rf_included=rf_included,
                rf_mode_current=rf_mode_current,
                response_format_current=response_format_current,
                structured_output_used=structured_output_used,
                structured_output_mode_used=structured_output_mode_used,
                sanitized_messages=sanitized_messages,
                on_stream_delta=on_stream_delta,
                started=started,
            )

        resp = await client.post("/chat/completions", headers=headers, json=body)
        try:
            await validate_response_size(resp, self._max_response_size_bytes, "OpenRouter")
        except ResponseSizeError as size_exc:
            latency = int((time.perf_counter() - started) * 1000)
            return {
                "success": False,
                "error_text": f"Response too large: {size_exc}",
                "latency": latency,
                "should_try_next_model": True,
            }

        latency = int((time.perf_counter() - started) * 1000)
        try:
            data = resp.json()
        except Exception as e:
            raise_if_cancelled(e)
            return {
                "success": False,
                "error_text": f"Failed to parse JSON response: {e}",
                "latency": latency,
                "should_try_next_model": True,
            }

        if self.payload_logger._debug_payloads:
            self.payload_logger.log_response_payload(data)

        status_code = resp.status_code
        model_reported = data.get("model", model) if isinstance(data, dict) else model

        # Handle successful response (200)
        if status_code == 200:
            return await self._handle_successful_response(
                data=data,
                rf_included=rf_included,
                rf_mode_current=rf_mode_current,
                response_format_current=response_format_current,
                model=model,
                model_reported=model_reported,
                latency=latency,
                attempt=attempt,
                request_id=request_id,
                structured_output_used=structured_output_used,
                structured_output_mode_used=structured_output_mode_used,
                headers=headers,
                sanitized_messages=sanitized_messages,
                max_tokens=request.max_tokens,
            )

        # Handle error responses
        return await self._handle_error_response(
            status_code=status_code,
            data=data,
            resp=resp,
            rf_included=rf_included,
            rf_mode_current=rf_mode_current,
            response_format_current=response_format_current,
            model=model,
            model_reported=model_reported,
            latency=latency,
            attempt=attempt,
            request_id=request_id,
            headers=headers,
            sanitized_messages=sanitized_messages,
        )

    except TimeoutError:
        latency = int((time.perf_counter() - started) * 1000)
        return {
            "success": False,
            "error_text": "Request timeout",
            "latency": latency,
            "model_reported": model,
            "error_context": {
                "status_code": None,
                "message": "Request timeout",
                "timeout": True,
            },
            "should_try_next_model": True,
        }
    except Exception as e:
        raise_if_cancelled(e)
        latency = int((time.perf_counter() - started) * 1000)
        return {
            "success": False,
            "error_text": str(e),
            "latency": latency,
            "should_retry": attempt < self.error_handler._max_retries,
            "backoff_needed": True,
        }


def _build_truncation_response(
    self,
    *,
    rf_included: bool,
    response_format_current: dict[str, Any] | None,
    rf_mode_current: str,
    attempt: int,
    text: Any,
    max_tokens: int | None,
) -> dict[str, Any]:
    current_max = max_tokens or 8192
    suggested_max = min(int(current_max * 1.5), 32768)
    truncation_recovery = {
        "original_max_tokens": current_max,
        "suggested_max_tokens": suggested_max,
    }

    if rf_included and response_format_current:
        if rf_mode_current == "json_schema":
            return {
                "success": False,
                "should_retry": True,
                "new_rf_mode": "json_object",
                "new_response_format": {"type": "json_object"},
                "backoff_needed": True,
                "structured_output_used": True,
                "structured_output_mode_used": "json_object",
                "truncation_recovery": truncation_recovery,
            }
        if rf_mode_current == "json_object":
            return {
                "success": False,
                "should_retry": True,
                "new_rf_mode": rf_mode_current,
                "new_response_format": None,
                "backoff_needed": True,
                "structured_output_used": False,
                "structured_output_mode_used": None,
                "truncation_recovery": truncation_recovery,
            }

    if attempt < self.error_handler._max_retries:
        return {
            "success": False,
            "should_retry": True,
            "backoff_needed": True,
            "truncation_recovery": truncation_recovery,
        }
    return {
        "success": False,
        "error_text": "completion_truncated",
        "response_text": text if isinstance(text, str) else None,
        "should_try_next_model": True,
        "truncation_recovery": truncation_recovery,
    }


def _validate_structured_success_payload(
    self,
    *,
    text: Any,
    rf_included: bool,
    response_format_current: dict[str, Any] | None,
    rf_mode_current: str,
    attempt: int,
    model: str,
) -> tuple[Any, dict[str, Any] | None]:
    if not (rf_included and response_format_current):
        return text, None

    is_valid, processed_text = self.response_processor.validate_structured_response(
        text, rf_included, response_format_current
    )
    if is_valid:
        return processed_text, None

    if rf_mode_current == "json_schema" and attempt < self.error_handler._max_retries:
        logger.warning(
            "structured_output_downgrading_json_schema_to_json_object",
            extra={"model": model, "attempt": attempt + 1},
        )
        return text, {
            "success": False,
            "should_retry": True,
            "new_rf_mode": "json_object",
            "new_response_format": {"type": "json_object"},
            "backoff_needed": True,
        }
    if rf_mode_current == "json_object" and attempt < self.error_handler._max_retries:
        logger.warning(
            "structured_output_disabling_after_json_object_failure",
            extra={"model": model, "attempt": attempt + 1},
        )
        return text, {
            "success": False,
            "should_retry": True,
            "new_rf_mode": None,
            "new_response_format": None,
            "backoff_needed": True,
        }
    return text, {
        "success": False,
        "error_text": "structured_output_parse_error",
        "response_text": processed_text or None,
        "structured_parse_error": True,
        "should_try_next_model": True,
    }


def _extract_finish_reason(data: dict[str, Any]) -> tuple[Any, Any]:
    finish_reason = None
    native_finish = None
    choices = data.get("choices") if isinstance(data, dict) else None
    if isinstance(choices, list) and choices:
        first_choice = choices[0] or {}
        if isinstance(first_choice, dict):
            finish_reason = first_choice.get("finish_reason")
            native_finish = first_choice.get("native_finish_reason")
    return finish_reason, native_finish


def _estimate_cost_if_missing(
    self,
    *,
    cost_usd: float | None,
    tokens_prompt: Any,
    tokens_completion: Any,
) -> float | None:
    if cost_usd is not None or tokens_prompt is None or tokens_completion is None:
        return cost_usd
    if self._price_input_per_1k is None or self._price_output_per_1k is None:
        return cost_usd
    try:
        return (float(tokens_prompt) / 1000.0) * self._price_input_per_1k + (
            float(tokens_completion) / 1000.0
        ) * self._price_output_per_1k
    except Exception:
        return None


def _build_successful_llm_result(
    *,
    data: dict[str, Any],
    model_reported: str,
    text: Any,
    tokens_prompt: Any,
    tokens_completion: Any,
    cost_usd: float | None,
    latency: int,
    redacted_headers: dict[str, str],
    sanitized_messages: list[dict[str, Any]],
    structured_output_used: bool,
    structured_output_mode_used: str | None,
    cache_metrics: Any,
) -> dict[str, Any]:
    return {
        "success": True,
        "llm_result": LLMCallResult(
            status="ok",
            model=model_reported,
            response_text=text,
            response_json=data,
            openrouter_response_text=text,
            openrouter_response_json=data,
            tokens_prompt=tokens_prompt,
            tokens_completion=tokens_completion,
            cost_usd=cost_usd,
            latency_ms=latency,
            error_text=None,
            request_headers=redacted_headers,
            request_messages=sanitized_messages,
            endpoint="/api/v1/chat/completions",
            structured_output_used=structured_output_used,
            structured_output_mode=structured_output_mode_used,
            cache_read_tokens=(
                cache_metrics.cache_read_tokens if cache_metrics.cache_read_tokens > 0 else None
            ),
            cache_creation_tokens=(
                cache_metrics.cache_creation_tokens
                if cache_metrics.cache_creation_tokens > 0
                else None
            ),
            cache_discount=cache_metrics.cache_discount,
        ),
    }


async def _handle_successful_response(
    self,
    data: dict[str, Any],
    rf_included: bool,
    rf_mode_current: str,
    response_format_current: dict[str, Any] | None,
    model: str,
    model_reported: str,
    latency: int,
    attempt: int,
    request_id: int | None,
    structured_output_used: bool,
    structured_output_mode_used: str | None,
    headers: dict[str, str],
    sanitized_messages: list[dict[str, Any]],
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Handle successful API response."""
    logger.debug(
        "processing_successful_response",
        extra={
            "model": model,
            "latency_ms": latency,
            "request_id": request_id,
            "rf_mode": rf_mode_current,
            "stage": "entry",
        },
    )

    # Extract response data
    text, usage, cost_usd = self.response_processor.extract_response_data(data, rf_included)

    logger.debug(
        "processing_successful_response",
        extra={
            "request_id": request_id,
            "stage": "checking_truncation",
            "text_len": len(text) if text else 0,
        },
    )

    truncated, truncated_finish, truncated_native = self.response_processor.is_completion_truncated(
        data
    )
    if truncated:
        self.error_handler.log_truncated_completion(
            model, truncated_finish, truncated_native, request_id
        )
        return _build_truncation_response(
            self,
            rf_included=rf_included,
            response_format_current=response_format_current,
            rf_mode_current=rf_mode_current,
            attempt=attempt,
            text=text,
            max_tokens=max_tokens,
        )

    if rf_included and response_format_current:
        logger.debug(
            "processing_successful_response",
            extra={
                "request_id": request_id,
                "stage": "validating_structured_output",
                "rf_mode": rf_mode_current,
            },
        )
        text, validation_result = _validate_structured_success_payload(
            self,
            text=text,
            rf_included=rf_included,
            response_format_current=response_format_current,
            rf_mode_current=rf_mode_current,
            attempt=attempt,
            model=model,
        )
        if validation_result is not None:
            return validation_result

    finish_reason, native_finish = _extract_finish_reason(data)
    tokens_prompt = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    tokens_completion = usage.get("completion_tokens") if isinstance(usage, dict) else None
    tokens_total = usage.get("total_tokens") if isinstance(usage, dict) else None

    cache_metrics = self.response_processor.extract_cache_metrics(data)
    if cache_metrics.cache_hit or cache_metrics.cache_creation_tokens > 0:
        logger.info(
            "prompt_cache_metrics",
            extra={
                "model": model_reported,
                "cache_read_tokens": cache_metrics.cache_read_tokens,
                "cache_creation_tokens": cache_metrics.cache_creation_tokens,
                "cache_discount": cache_metrics.cache_discount,
                "cache_hit": cache_metrics.cache_hit,
                "request_id": request_id,
            },
        )

    cost_usd = _estimate_cost_if_missing(
        self,
        cost_usd=cost_usd,
        tokens_prompt=tokens_prompt,
        tokens_completion=tokens_completion,
    )

    # Log successful response
    self.payload_logger.log_response(
        status=200,
        latency_ms=latency,
        model=model_reported,
        attempt=attempt,
        request_id=request_id,
        truncated=truncated,
        finish_reason=finish_reason,
        native_finish_reason=native_finish,
        tokens_prompt=tokens_prompt,
        tokens_completion=tokens_completion,
        tokens_total=tokens_total,
        cost_usd=cost_usd,
        structured_output=rf_included,
        rf_mode=rf_mode_current,
    )

    self.error_handler.log_success(
        attempt,
        model,
        200,
        latency,
        structured_output_used,
        structured_output_mode_used,
        request_id,
    )

    redacted_headers = self.request_builder.get_redacted_headers(headers)
    return _build_successful_llm_result(
        data=data,
        model_reported=model_reported,
        text=text,
        tokens_prompt=tokens_prompt,
        tokens_completion=tokens_completion,
        cost_usd=cost_usd,
        latency=latency,
        redacted_headers=redacted_headers,
        sanitized_messages=sanitized_messages,
        structured_output_used=structured_output_used,
        structured_output_mode_used=structured_output_mode_used,
        cache_metrics=cache_metrics,
    )


def _maybe_downgrade_on_response_format_error(
    self,
    *,
    status_code: int,
    data: dict[str, Any],
    rf_included: bool,
    rf_mode_current: str,
    attempt: int,
    model: str,
    request_id: int | None,
) -> dict[str, Any] | None:
    if not self.response_processor.should_downgrade_response_format(status_code, data, rf_included):
        return None

    should_downgrade, new_mode = self.error_handler.should_downgrade_response_format(
        status_code, data, rf_mode_current, rf_included, attempt
    )
    if not should_downgrade:
        return None
    if new_mode:
        self.error_handler.log_response_format_downgrade(model, "json_schema", new_mode, request_id)
        return {
            "success": False,
            "should_retry": True,
            "new_rf_mode": new_mode,
            "new_response_format": {"type": "json_object"} if new_mode == "json_object" else None,
            "backoff_needed": True,
        }

    self.error_handler.log_structured_outputs_disabled(model, request_id)
    return {
        "success": False,
        "should_retry": True,
        "new_rf_mode": rf_mode_current,
        "new_response_format": None,
        "structured_output_used": False,
        "structured_output_mode_used": None,
        "backoff_needed": True,
    }


def _maybe_downgrade_on_endpoint_capability_error(
    self,
    *,
    status_code: int,
    error_message: str,
    error_context: dict[str, Any],
    rf_included: bool,
    response_format_current: dict[str, Any] | None,
    rf_mode_current: str,
    model: str,
    request_id: int | None,
) -> dict[str, Any] | None:
    api_error_lower = str(error_context.get("api_error", "")).lower()
    if not (
        rf_included
        and response_format_current
        and (
            status_code == 404
            or "no endpoints found" in error_message.lower()
            or "no endpoints found" in api_error_lower
            or "does not support structured" in api_error_lower
        )
    ):
        return None

    if rf_mode_current == "json_schema":
        self.error_handler.log_response_format_downgrade(
            model, "json_schema", "json_object", request_id
        )
        return {
            "success": False,
            "should_retry": True,
            "new_rf_mode": "json_object",
            "new_response_format": {"type": "json_object"},
            "backoff_needed": True,
        }
    if rf_mode_current == "json_object":
        self.error_handler.log_structured_outputs_disabled(model, request_id)
        return {
            "success": False,
            "should_retry": True,
            "new_rf_mode": rf_mode_current,
            "new_response_format": None,
            "structured_output_used": False,
            "structured_output_mode_used": None,
            "backoff_needed": True,
        }
    return None


async def _handle_error_response(
    self,
    status_code: int,
    data: dict[str, Any],
    resp: httpx.Response,
    rf_included: bool,
    rf_mode_current: str,
    response_format_current: dict[str, Any] | None,
    model: str,
    model_reported: str,
    latency: int,
    attempt: int,
    request_id: int | None,
    headers: dict[str, str],
    sanitized_messages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Handle error responses with appropriate retry/fallback logic."""
    downgrade_result = _maybe_downgrade_on_response_format_error(
        self,
        status_code=status_code,
        data=data,
        rf_included=rf_included,
        rf_mode_current=rf_mode_current,
        attempt=attempt,
        model=model,
        request_id=request_id,
    )
    if downgrade_result is not None:
        return downgrade_result

    # Extract response content and error context
    text, usage, _ = self.response_processor.extract_response_data(data, rf_included)
    error_context = self.response_processor.get_error_context(status_code, data)
    error_message = str(error_context["message"])

    # Prepare redacted headers
    redacted_headers = self.request_builder.get_redacted_headers(headers)

    # Non-retryable errors
    if self.error_handler.is_non_retryable_error(status_code):
        error_message = self._get_error_message(status_code, data)
        return {
            "success": False,
            "error_result": self.error_handler.build_error_result(
                model_reported,
                text,
                data,
                usage,
                latency,
                error_message,
                redacted_headers,
                sanitized_messages,
                error_context=error_context,
            ),
        }

    # 404 / 408 / 504 / timeout text: Try next model if available
    if self.error_handler.should_try_next_model(status_code, error_message):
        structured_downgrade = _maybe_downgrade_on_endpoint_capability_error(
            self,
            status_code=status_code,
            error_message=error_message,
            error_context=error_context,
            rf_included=rf_included,
            response_format_current=response_format_current,
            rf_mode_current=rf_mode_current,
            model=model,
            request_id=request_id,
        )
        if structured_downgrade is not None:
            return structured_downgrade

        # Log and try next model
        self.error_handler.log_error(attempt, model, status_code, error_message, request_id, "WARN")
        return {
            "success": False,
            "error_text": error_message,
            "data": data,
            "latency": latency,
            "model_reported": model_reported,
            "error_context": error_context,
            "should_try_next_model": True,
        }

    # Retryable errors
    if self.error_handler.should_retry(status_code, attempt):
        if status_code == 429:
            await self.error_handler.handle_rate_limit(resp.headers)
        return {
            "success": False,
            "should_retry": True,
            "backoff_needed": status_code != 429,  # Rate limit handling already done
            "error_text": error_message,
            "error_context": error_context,
        }

    # Unknown/unhandled error - try next model
    self.error_handler.log_error(attempt, model, status_code, error_message, request_id)
    return {
        "success": False,
        "error_text": error_message,
        "data": data,
        "latency": latency,
        "model_reported": model_reported,
        "error_context": error_context,
        "should_try_next_model": True,
    }
