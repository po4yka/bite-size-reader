from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from app.adapters.openrouter.chat_models import (
    AttemptOutcome,
    AttemptRequestPayload,
    StreamingState,
)
from app.core.async_utils import raise_if_cancelled
from app.core.logging_utils import get_logger
from app.observability.metrics import record_draft_stream_event, record_stream_latency_ms

if TYPE_CHECKING:
    from app.adapters.openrouter.chat_response_handler import ChatResponseHandler
    from app.models.llm.llm_models import ChatRequest

logger = get_logger(__name__)


class ChatStreamingHandler:
    def __init__(self, response_handler: ChatResponseHandler | Any) -> None:
        self._response_handler = response_handler

    async def consume_stream_sse(
        self,
        resp: Any,
        *,
        process_event_payload: Any,
    ) -> None:
        current_event_data_lines: list[str] = []
        async for line in resp.aiter_lines():
            if line == "":
                if not current_event_data_lines:
                    continue
                payload = "\n".join(current_event_data_lines).strip()
                current_event_data_lines.clear()
                if await process_event_payload(payload):
                    return
                continue

            if line.startswith("data:"):
                payload_line = line[5:].lstrip()
                if current_event_data_lines:
                    buffered_payload = "\n".join(current_event_data_lines).strip()
                    if await process_event_payload(buffered_payload):
                        return
                    current_event_data_lines.clear()
                current_event_data_lines.append(payload_line)

        if current_event_data_lines:
            payload = "\n".join(current_event_data_lines).strip()
            await process_event_payload(payload)

    async def process_stream_event_payload(
        self,
        *,
        payload: str,
        state: StreamingState,
        model: str,
        started: float,
        on_stream_delta: Any | None,
        request_id: int | None,
    ) -> bool:
        payload = payload.strip()
        if not payload:
            return False
        if payload == "[DONE]":
            state.done_received = True
            return True

        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            state.malformed_frames += 1
            return False
        if not isinstance(chunk, dict):
            state.malformed_frames += 1
            return False

        state.last_chunk = chunk
        state.model_reported = chunk.get("model", state.model_reported or model)
        usage_chunk = chunk.get("usage")
        if isinstance(usage_chunk, dict):
            state.usage = usage_chunk

        choices = chunk.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0] if isinstance(choices[0], dict) else {}
            state.finish_reason = first_choice.get("finish_reason") or state.finish_reason
            state.native_finish_reason = (
                first_choice.get("native_finish_reason") or state.native_finish_reason
            )

        delta_text = self.extract_stream_delta_text(chunk)
        if not delta_text:
            return False
        if state.first_token_ms is None:
            state.first_token_ms = int((time.perf_counter() - started) * 1000)
            record_stream_latency_ms("stream_first_token_ms", state.first_token_ms)
        state.stream_text_parts.append(delta_text)
        state.stream_delta_count += 1
        record_draft_stream_event("stream_delta_count")
        try:
            await self._dispatch_stream_delta(on_stream_delta, delta_text)
        except Exception as callback_exc:
            raise_if_cancelled(callback_exc)
            logger.warning(
                "openrouter_stream_delta_callback_failed",
                extra={"error": str(callback_exc), "request_id": request_id},
            )
        return False

    def finalize_stream_success(
        self,
        *,
        attempt: int,
        request_id: int | None,
        model: str,
        request: ChatRequest,
        payload: AttemptRequestPayload,
        sanitized_messages: list[dict[str, Any]],
        started: float,
        state: StreamingState,
    ) -> AttemptOutcome:
        completion_ms = int((time.perf_counter() - started) * 1000)
        record_stream_latency_ms("stream_completion_ms", completion_ms)

        full_text = "".join(state.stream_text_parts)
        if not full_text and isinstance(state.last_chunk, dict):
            full_text = self.extract_stream_delta_text(state.last_chunk)
        if not full_text:
            return self.build_stream_empty_outcome(
                completion_ms=completion_ms,
                payload=payload,
            )

        if state.malformed_frames > 0:
            logger.warning(
                "openrouter_stream_malformed_frames",
                extra={
                    "request_id": request_id,
                    "model": state.model_reported,
                    "malformed_frames": state.malformed_frames,
                },
            )

        synthesized_data = self.build_stream_synthesized_data(
            request_id=request_id,
            model_reported=state.model_reported,
            full_text=full_text,
            done_received=state.done_received,
            finish_reason=state.finish_reason,
            native_finish_reason=state.native_finish_reason,
            usage=state.usage,
        )
        logger.info(
            "openrouter_stream_complete",
            extra={
                "request_id": request_id,
                "model": state.model_reported,
                "stream_delta_count": state.stream_delta_count,
                "stream_first_token_ms": state.first_token_ms,
                "stream_completion_ms": completion_ms,
            },
        )
        return self._response_handler.handle_successful_response(
            data=synthesized_data,
            payload=payload,
            model=model,
            model_reported=state.model_reported,
            latency=completion_ms,
            attempt=attempt,
            request_id=request_id,
            sanitized_messages=sanitized_messages,
            max_tokens=request.max_tokens,
        )

    def build_stream_empty_outcome(
        self,
        *,
        completion_ms: int,
        payload: AttemptRequestPayload,
    ) -> AttemptOutcome:
        from app.adapters.openrouter.chat_models import RetryDirective

        return AttemptOutcome(
            error_text="stream_empty_completion",
            latency=completion_ms,
            retry=RetryDirective(
                rf_mode=payload.rf_mode_current,
                response_format=payload.response_format_current,
                backoff_needed=False,
                fallback_to_non_stream=True,
            ),
            structured_output_state=payload.structured_output_state,
        )

    def build_stream_synthesized_data(
        self,
        *,
        request_id: int | None,
        model_reported: str,
        full_text: str,
        done_received: bool,
        finish_reason: str | None,
        native_finish_reason: str | None,
        usage: dict[str, Any] | None,
    ) -> dict[str, Any]:
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
        return synthesized_data

    def extract_stream_delta_text(self, data: dict[str, Any]) -> str:
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

        message = first_choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
        return ""

    async def _dispatch_stream_delta(
        self,
        on_stream_delta: Any | None,
        delta_text: str,
    ) -> None:
        if not on_stream_delta or not delta_text:
            return
        callback_result = on_stream_delta(delta_text)
        if hasattr(callback_result, "__await__"):
            await callback_result
