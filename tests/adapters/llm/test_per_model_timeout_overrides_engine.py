"""Tests for per-model timeout override logic in OpenRouterChatEngine."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapter_models.llm.llm_models import LLMCallResult
from app.adapters.openrouter.chat_engine import OpenRouterChatEngine
from app.core.call_status import CallStatus


def _make_client() -> MagicMock:
    client = MagicMock()
    client._closed = False
    client._circuit_breaker = None
    client._request_context = MagicMock()
    client.error_handler = MagicMock()
    client.error_handler._max_retries = 0
    client.error_handler.log_exhausted = MagicMock()
    client.error_handler.log_fallback = MagicMock()
    return client


def _make_success_result(model: str = "test-model") -> LLMCallResult:
    return LLMCallResult(
        status=CallStatus.OK,
        model=model,
        response_text="ok",
        tokens_prompt=10,
        tokens_completion=10,
        cost_usd=0.001,
        latency_ms=500,
    )


@pytest.mark.asyncio
async def test_per_model_override_beats_base_timeout() -> None:
    """When an override is set for a model, the engine uses it instead of the base timeout."""
    captured_timeouts: list[float | None] = []

    original_timeout = asyncio.timeout

    def patched_timeout(delay: float | None) -> Any:
        captured_timeouts.append(delay)
        return original_timeout(delay)

    client = _make_client()
    engine = OpenRouterChatEngine(client)

    success_result = _make_success_result("slow-model/v1")

    # Build a mock context that returns one model.
    mock_context = MagicMock()
    mock_context.models_to_try = ["slow-model/v1"]
    mock_context.request = MagicMock()
    mock_context.sanitized_messages = []
    mock_context.message_lengths = []
    mock_context.message_roles = []
    mock_context.total_chars = 0
    mock_context.primary_model = "slow-model/v1"
    mock_context.initial_rf_mode = "json_object"
    mock_context.response_format_initial = None

    mock_model_state = MagicMock()
    mock_model_state.terminal_result = success_result
    mock_model_state.request = mock_context.request
    mock_model_state.structured_output_state = MagicMock()
    mock_model_state.structured_output_state.parse_error = False
    mock_model_state.last_error_text = None
    mock_model_state.last_data = None
    mock_model_state.last_latency = 500
    mock_model_state.last_model_reported = "slow-model/v1"
    mock_model_state.last_response_text = "ok"
    mock_model_state.last_error_context = None

    with (
        patch.object(engine._context_builder, "prepare", return_value=mock_context),
        patch.object(
            engine._context_builder,
            "maybe_skip_unsupported_structured_model",
            new=AsyncMock(return_value=(False, MagicMock())),
        ),
        patch.object(
            engine._attempt_runner,
            "run_attempts_for_model",
            new=AsyncMock(return_value=mock_model_state),
        ),
        patch("asyncio.timeout", side_effect=patched_timeout),
    ):
        http_ctx = AsyncMock()
        http_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        http_ctx.__aexit__ = AsyncMock(return_value=False)
        client._request_context.return_value = http_ctx

        result = await engine.chat(
            [{"role": "user", "content": "hello"}],
            per_model_timeout_sec=60.0,
            per_model_timeout_overrides={"slow-model/v1": 240.0},
        )

    # The override (240) should win over the base (60).
    assert 240.0 in captured_timeouts
    assert 60.0 not in captured_timeouts
    assert result.status == CallStatus.OK
    # models_attempted should record the success
    assert result.models_attempted == [("slow-model/v1", "success")]


@pytest.mark.asyncio
async def test_base_timeout_used_when_no_override() -> None:
    """When a model has no override, the base per_model_timeout_sec is used."""
    captured_timeouts: list[float | None] = []

    original_timeout = asyncio.timeout

    def patched_timeout(delay: float | None) -> Any:
        captured_timeouts.append(delay)
        return original_timeout(delay)

    client = _make_client()
    engine = OpenRouterChatEngine(client)

    success_result = _make_success_result("fast-model/v1")

    mock_context = MagicMock()
    mock_context.models_to_try = ["fast-model/v1"]
    mock_context.request = MagicMock()
    mock_context.sanitized_messages = []
    mock_context.message_lengths = []
    mock_context.message_roles = []
    mock_context.total_chars = 0
    mock_context.primary_model = "fast-model/v1"
    mock_context.initial_rf_mode = "json_object"
    mock_context.response_format_initial = None

    mock_model_state = MagicMock()
    mock_model_state.terminal_result = success_result
    mock_model_state.request = mock_context.request
    mock_model_state.structured_output_state = MagicMock()
    mock_model_state.structured_output_state.parse_error = False
    mock_model_state.last_error_text = None
    mock_model_state.last_data = None
    mock_model_state.last_latency = 300
    mock_model_state.last_model_reported = "fast-model/v1"
    mock_model_state.last_response_text = "ok"
    mock_model_state.last_error_context = None

    with (
        patch.object(engine._context_builder, "prepare", return_value=mock_context),
        patch.object(
            engine._context_builder,
            "maybe_skip_unsupported_structured_model",
            new=AsyncMock(return_value=(False, MagicMock())),
        ),
        patch.object(
            engine._attempt_runner,
            "run_attempts_for_model",
            new=AsyncMock(return_value=mock_model_state),
        ),
        patch("asyncio.timeout", side_effect=patched_timeout),
    ):
        http_ctx = AsyncMock()
        http_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        http_ctx.__aexit__ = AsyncMock(return_value=False)
        client._request_context.return_value = http_ctx

        result = await engine.chat(
            [{"role": "user", "content": "hello"}],
            per_model_timeout_sec=90.0,
            # overrides dict does NOT contain this model
            per_model_timeout_overrides={"other-model/v1": 240.0},
        )

    # Base timeout (90) should be used for fast-model/v1.
    assert 90.0 in captured_timeouts
    assert 240.0 not in captured_timeouts
    assert result.status == CallStatus.OK


@pytest.mark.asyncio
async def test_models_attempted_timeout_tracked() -> None:
    """Timed-out models appear in models_attempted with 'timeout' outcome."""
    client = _make_client()
    engine = OpenRouterChatEngine(client)

    mock_context = MagicMock()
    mock_context.models_to_try = ["slow-model/v1"]
    mock_context.request = MagicMock()
    mock_context.sanitized_messages = []
    mock_context.message_lengths = []
    mock_context.message_roles = []
    mock_context.total_chars = 0
    mock_context.primary_model = "slow-model/v1"
    mock_context.initial_rf_mode = "json_object"
    mock_context.response_format_initial = None

    exhausted_result = LLMCallResult(
        status=CallStatus.ERROR,
        model="slow-model/v1",
        error_text="timed out",
        tokens_prompt=None,
        tokens_completion=None,
        cost_usd=None,
        latency_ms=None,
    )

    with (
        patch.object(engine._context_builder, "prepare", return_value=mock_context),
        patch.object(
            engine._context_builder,
            "maybe_skip_unsupported_structured_model",
            # Raise TimeoutError to simulate a per-model timeout.
            new=AsyncMock(side_effect=TimeoutError),
        ),
        patch.object(
            engine._attempt_runner,
            "build_exhausted_chat_result",
            return_value=exhausted_result,
        ) as mock_build,
    ):
        http_ctx = AsyncMock()
        http_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        http_ctx.__aexit__ = AsyncMock(return_value=False)
        client._request_context.return_value = http_ctx

        result = await engine.chat(
            [{"role": "user", "content": "hello"}],
            per_model_timeout_sec=0.001,
        )

    # build_exhausted_chat_result was called; models_attempted should record timeout.
    assert mock_build.called
    call_kwargs = mock_build.call_args.kwargs
    attempted = call_kwargs.get("models_attempted", [])
    assert any(outcome == "timeout" for _, outcome in attempted)
