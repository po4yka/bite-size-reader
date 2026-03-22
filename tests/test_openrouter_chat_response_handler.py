from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.adapters.openrouter.chat_models import AttemptRequestPayload, StructuredOutputState
from app.adapters.openrouter.chat_response_handler import ChatResponseHandler
from app.adapters.openrouter.openrouter_client import OpenRouterClient


def _make_client() -> OpenRouterClient:
    from app.adapters.openrouter.openrouter_client import OpenRouterClientConfig

    client = OpenRouterClient(
        api_key="sk-or-test-key",
        model="qwen/qwen3-max",
        config=OpenRouterClientConfig(max_retries=2, enable_stats=True),
    )
    client._price_input_per_1k = 0.001
    client._price_output_per_1k = 0.002
    return client


def _make_payload(
    *,
    rf_included: bool = False,
    rf_mode_current: str | None = None,
    response_format_current: dict | None = None,
    structured_output_state: StructuredOutputState | None = None,
) -> AttemptRequestPayload:
    return AttemptRequestPayload(
        cacheable_messages=[],
        headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
        body={},
        rf_included=rf_included,
        rf_mode_current=rf_mode_current,
        response_format_current=response_format_current,
        structured_output_state=structured_output_state or StructuredOutputState(),
    )


@pytest.mark.asyncio
async def test_chat_response_handler_returns_success_for_valid_structured_payload() -> None:
    handler = ChatResponseHandler(_make_client())
    outcome = handler.handle_successful_response(
        data={
            "model": "qwen/qwen3-max",
            "choices": [{"message": {"content": '{"summary_250":"ok"}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
        payload=_make_payload(
            rf_included=True,
            rf_mode_current="json_object",
            response_format_current={"type": "json_object"},
            structured_output_state=StructuredOutputState(used=True, mode="json_object"),
        ),
        model="qwen/qwen3-max",
        model_reported="qwen/qwen3-max",
        latency=20,
        attempt=0,
        request_id=1,
        sanitized_messages=[{"role": "user", "content": "hello"}],
        max_tokens=128,
    )

    assert outcome.success is True
    assert outcome.llm_result is not None
    assert outcome.llm_result.structured_output_mode == "json_object"


@pytest.mark.asyncio
async def test_chat_response_handler_downgrades_invalid_json_schema_then_disables_json_object() -> (
    None
):
    handler = ChatResponseHandler(_make_client())

    schema_outcome = handler.handle_successful_response(
        data={
            "model": "qwen/qwen3-max",
            "choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
        payload=_make_payload(
            rf_included=True,
            rf_mode_current="json_schema",
            response_format_current={"type": "json_schema"},
            structured_output_state=StructuredOutputState(used=True, mode="json_schema"),
        ),
        model="qwen/qwen3-max",
        model_reported="qwen/qwen3-max",
        latency=20,
        attempt=0,
        request_id=2,
        sanitized_messages=[{"role": "user", "content": "hello"}],
        max_tokens=128,
    )
    assert schema_outcome.retry is not None
    assert schema_outcome.retry.rf_mode == "json_object"

    object_outcome = handler.handle_successful_response(
        data={
            "model": "qwen/qwen3-max",
            "choices": [{"message": {"content": "still not json"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
        payload=_make_payload(
            rf_included=True,
            rf_mode_current="json_object",
            response_format_current={"type": "json_object"},
            structured_output_state=StructuredOutputState(used=True, mode="json_object"),
        ),
        model="qwen/qwen3-max",
        model_reported="qwen/qwen3-max",
        latency=20,
        attempt=0,
        request_id=3,
        sanitized_messages=[{"role": "user", "content": "hello"}],
        max_tokens=128,
    )
    assert object_outcome.retry is not None
    assert object_outcome.retry.response_format is None
    assert object_outcome.structured_output_state is not None
    assert object_outcome.structured_output_state.used is False


@pytest.mark.asyncio
async def test_chat_response_handler_downgrades_endpoint_capability_errors() -> None:
    handler = ChatResponseHandler(_make_client())

    outcome = await handler.handle_error_response(
        status_code=404,
        data={"error": {"message": "This provider does not support structured outputs"}},
        resp=SimpleNamespace(headers={}),
        payload=_make_payload(
            rf_included=True,
            rf_mode_current="json_schema",
            response_format_current={"type": "json_schema"},
            structured_output_state=StructuredOutputState(used=True, mode="json_schema"),
        ),
        model="qwen/qwen3-max",
        model_reported="qwen/qwen3-max",
        latency=35,
        attempt=0,
        request_id=4,
        sanitized_messages=[{"role": "user", "content": "hello"}],
    )

    assert outcome.retry is not None
    assert outcome.retry.rf_mode == "json_object"


@pytest.mark.asyncio
async def test_chat_response_handler_builds_non_retryable_error_results() -> None:
    handler = ChatResponseHandler(_make_client())

    outcome = await handler.handle_error_response(
        status_code=401,
        data={"error": {"message": "Invalid API key"}},
        resp=SimpleNamespace(headers={}),
        payload=_make_payload(),
        model="qwen/qwen3-max",
        model_reported="qwen/qwen3-max",
        latency=10,
        attempt=0,
        request_id=5,
        sanitized_messages=[{"role": "user", "content": "hello"}],
    )

    assert outcome.error_result is not None
    assert outcome.error_result.status == "error"
    assert "Authentication failed" in (outcome.error_result.error_text or "")


@pytest.mark.asyncio
async def test_chat_response_handler_retries_server_errors_and_tries_next_model_on_timeout() -> (
    None
):
    handler = ChatResponseHandler(_make_client())

    retry_outcome = await handler.handle_error_response(
        status_code=500,
        data={"error": {"message": "upstream failure"}},
        resp=SimpleNamespace(headers={}),
        payload=_make_payload(),
        model="qwen/qwen3-max",
        model_reported="qwen/qwen3-max",
        latency=50,
        attempt=0,
        request_id=6,
        sanitized_messages=[{"role": "user", "content": "hello"}],
    )
    assert retry_outcome.retry is not None
    assert retry_outcome.retry.backoff_needed is True

    next_model_outcome = await handler.handle_error_response(
        status_code=504,
        data={"error": {"message": "gateway timeout"}},
        resp=SimpleNamespace(headers={}),
        payload=_make_payload(),
        model="qwen/qwen3-max",
        model_reported="qwen/qwen3-max",
        latency=75,
        attempt=0,
        request_id=7,
        sanitized_messages=[{"role": "user", "content": "hello"}],
    )
    assert next_model_outcome.should_try_next_model is True


@pytest.mark.asyncio
async def test_chat_response_handler_estimates_cost_and_propagates_cache_metrics() -> None:
    handler = ChatResponseHandler(_make_client())

    outcome = handler.handle_successful_response(
        data={
            "model": "qwen/qwen3-max",
            "choices": [{"message": {"content": "plain text"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": 25,
            },
        },
        payload=_make_payload(),
        model="qwen/qwen3-max",
        model_reported="qwen/qwen3-max",
        latency=15,
        attempt=0,
        request_id=8,
        sanitized_messages=[{"role": "user", "content": "hello"}],
        max_tokens=128,
    )

    assert outcome.llm_result is not None
    assert outcome.llm_result.cost_usd == pytest.approx(0.002)
    assert outcome.llm_result.cache_read_tokens == 100
    assert outcome.llm_result.cache_creation_tokens == 25
