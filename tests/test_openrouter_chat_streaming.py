from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapter_models.llm.llm_models import ChatRequest
from app.adapters.openrouter.chat_models import (
    AttemptOutcome,
    AttemptRequestPayload,
    StreamingState,
    StructuredOutputState,
)
from app.adapters.openrouter.chat_streaming import ChatStreamingHandler


class _StreamResponse:
    def __init__(self, lines: list[str]):
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def _make_payload() -> AttemptRequestPayload:
    return AttemptRequestPayload(
        cacheable_messages=[],
        headers={"Authorization": "Bearer test"},
        body={},
        rf_included=False,
        rf_mode_current=None,
        response_format_current=None,
        structured_output_state=StructuredOutputState(),
    )


def _make_request() -> ChatRequest:
    return ChatRequest(
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_tokens=128,
        top_p=None,
        stream=True,
        request_id=1,
        response_format=None,
        model_override=None,
    )


@pytest.mark.asyncio
async def test_chat_streaming_reconstructs_normal_sse_flow() -> None:
    response_handler = SimpleNamespace(
        handle_successful_response=MagicMock(
            return_value=AttemptOutcome(success=True, response_text="done")
        )
    )
    handler = ChatStreamingHandler(response_handler)
    state = StreamingState(model_reported="qwen/qwen3-max")

    async def process_payload(raw_payload: str) -> bool:
        return await handler.process_stream_event_payload(
            payload=raw_payload,
            state=state,
            model="qwen/qwen3-max",
            started=0.0,
            on_stream_delta=None,
            request_id=10,
        )

    await handler.consume_stream_sse(
        _StreamResponse(
            [
                'data: {"model":"qwen/qwen3-max","choices":[{"delta":{"content":"Hello "}}]}',
                'data: {"choices":[{"delta":{"content":"world"},"finish_reason":"stop"}],"usage":{"prompt_tokens":2,"completion_tokens":1}}',
                "data: [DONE]",
                "",
            ]
        ),
        process_event_payload=process_payload,
    )
    handler.finalize_stream_success(
        attempt=0,
        request_id=10,
        model="qwen/qwen3-max",
        request=_make_request(),
        payload=_make_payload(),
        sanitized_messages=[{"role": "user", "content": "hello"}],
        started=0.0,
        state=state,
    )

    call = response_handler.handle_successful_response.call_args.kwargs
    assert call["data"]["choices"][0]["message"]["content"] == "Hello world"
    assert call["data"]["usage"]["completion_tokens"] == 1


@pytest.mark.asyncio
async def test_chat_streaming_tolerates_malformed_frames() -> None:
    response_handler = SimpleNamespace(
        handle_successful_response=MagicMock(
            return_value=AttemptOutcome(success=True, response_text="done")
        )
    )
    handler = ChatStreamingHandler(response_handler)
    state = StreamingState(model_reported="qwen/qwen3-max")

    async def process_payload(raw_payload: str) -> bool:
        return await handler.process_stream_event_payload(
            payload=raw_payload,
            state=state,
            model="qwen/qwen3-max",
            started=0.0,
            on_stream_delta=None,
            request_id=11,
        )

    await handler.consume_stream_sse(
        _StreamResponse(
            [
                "data: {bad json}",
                'data: {"choices":[{"delta":{"content":"Recovered"},"finish_reason":"stop"}]}',
                "data: [DONE]",
                "",
            ]
        ),
        process_event_payload=process_payload,
    )
    handler.finalize_stream_success(
        attempt=0,
        request_id=11,
        model="qwen/qwen3-max",
        request=_make_request(),
        payload=_make_payload(),
        sanitized_messages=[{"role": "user", "content": "hello"}],
        started=0.0,
        state=state,
    )

    assert state.malformed_frames == 1
    call = response_handler.handle_successful_response.call_args.kwargs
    assert call["data"]["choices"][0]["message"]["content"] == "Recovered"


@pytest.mark.asyncio
async def test_chat_streaming_logs_and_ignores_delta_callback_failures(caplog) -> None:
    response_handler = SimpleNamespace(handle_successful_response=AsyncMock())
    handler = ChatStreamingHandler(response_handler)
    state = StreamingState(model_reported="qwen/qwen3-max")

    async def failing_callback(delta: str) -> None:
        raise RuntimeError(f"boom:{delta}")

    with caplog.at_level("WARNING"):
        done = await handler.process_stream_event_payload(
            payload='{"choices":[{"delta":{"content":"chunk"}}]}',
            state=state,
            model="qwen/qwen3-max",
            started=0.0,
            on_stream_delta=failing_callback,
            request_id=12,
        )

    assert done is False
    assert state.stream_text_parts == ["chunk"]
    assert "openrouter_stream_delta_callback_failed" in caplog.text


def test_chat_streaming_empty_completion_triggers_non_stream_fallback() -> None:
    response_handler = SimpleNamespace(handle_successful_response=AsyncMock())
    handler = ChatStreamingHandler(response_handler)

    outcome = handler.build_stream_empty_outcome(
        completion_ms=25,
        payload=_make_payload(),
    )

    assert outcome.error_text == "stream_empty_completion"
    assert outcome.retry is not None
    assert outcome.retry.fallback_to_non_stream is True
