"""Unit tests for budget-tight truncation-recovery guard (Improvement C).

Verifies that run_attempts_for_model breaks out of the retry loop with
``truncation_recovery_skipped_budget_tight`` when more than 60% of the
per-model time budget has been consumed before a truncation retry.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapter_models.llm.llm_models import ChatRequest
from app.adapters.openrouter.chat_attempt_runner import ChatAttemptRunner
from app.adapters.openrouter.chat_models import (
    AttemptOutcome,
    RetryDirective,
    StructuredOutputState,
    TruncationRecovery,
)
from app.adapters.openrouter.openrouter_client import OpenRouterClient, OpenRouterClientConfig

_TRUNCATION_OUTCOME = AttemptOutcome(
    retry=RetryDirective(
        rf_mode="json_schema",
        response_format={"type": "json_object"},
        backoff_needed=False,
        truncation_recovery=TruncationRecovery(
            original_max_tokens=100,
            suggested_max_tokens=200,
        ),
    ),
    structured_output_state=StructuredOutputState(used=True, mode="json_schema"),
)

_SUCCESS_OUTCOME = AttemptOutcome(
    success=True,
    llm_result=MagicMock(status="ok"),
    structured_output_state=StructuredOutputState(used=True, mode="json_schema"),
)


def _make_client() -> OpenRouterClient:
    return OpenRouterClient(
        api_key="sk-or-test-key",
        model="qwen/qwen3-max",
        config=OpenRouterClientConfig(max_retries=2),
    )


def _make_request(*, max_tokens: int | None = 100) -> ChatRequest:
    return ChatRequest(
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_tokens=max_tokens,
        top_p=None,
        stream=False,
        request_id=42,
        response_format={"type": "json_object"},
        model_override=None,
    )


def _common_kwargs(request: ChatRequest | None = None) -> dict:
    return {
        "client": MagicMock(),
        "model": "qwen/qwen3-max",
        "request": request or _make_request(max_tokens=100),
        "sanitized_messages": [{"role": "user", "content": "hello"}],
        "message_lengths": [5],
        "message_roles": ["user"],
        "total_chars": 5,
        "request_id": 42,
        "initial_rf_mode": "json_schema",
        "response_format_initial": {"type": "json_object"},
        "structured_output_state": StructuredOutputState(),
    }


@pytest.mark.asyncio
async def test_truncation_recovery_skipped_when_budget_over_60_percent() -> None:
    """When >60% of per_model_timeout_sec is elapsed, truncation retry is skipped."""
    client = _make_client()
    runner = ChatAttemptRunner(client, MagicMock())

    # Mock _attempt_transport directly (bypasses tenacity wrapper).
    runner._attempt_transport = AsyncMock(return_value=_TRUNCATION_OUTCOME)  # type: ignore[method-assign]

    # Simulate: model_started=0.0, budget-check call returns 0.7 (70% of 1.0s).
    _monotonic_values = iter([0.0, 0.7])

    with patch("app.adapters.openrouter.chat_attempt_runner.time") as mock_time:
        mock_time.monotonic.side_effect = lambda: next(_monotonic_values)
        state = await runner.run_attempts_for_model(
            **_common_kwargs(),
            per_model_timeout_sec=1.0,
        )

    assert state.last_error_text == "truncation_recovery_skipped_budget_tight"
    assert state.last_error_context == {"reason": "budget_tight"}
    # The guard fired after the first attempt — no retry happened.
    runner._attempt_transport.assert_awaited_once()


@pytest.mark.asyncio
async def test_truncation_recovery_proceeds_when_budget_under_60_percent() -> None:
    """When <60% of budget is elapsed, truncation retry is allowed (normal path)."""
    client = _make_client()
    runner = ChatAttemptRunner(client, MagicMock())

    runner._attempt_transport = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_TRUNCATION_OUTCOME, _SUCCESS_OUTCOME]
    )

    # Simulate: model_started=0.0, budget-check returns 0.3 (30% of 1.0s).
    _monotonic_values = iter([0.0, 0.3])

    with patch("app.adapters.openrouter.chat_attempt_runner.time") as mock_time:
        mock_time.monotonic.side_effect = lambda: next(_monotonic_values)
        state = await runner.run_attempts_for_model(
            **_common_kwargs(),
            per_model_timeout_sec=1.0,
        )

    # Budget was not tight — truncation retry was allowed and the second attempt succeeded.
    assert state.terminal_result is not None
    assert runner._attempt_transport.await_count == 2


@pytest.mark.asyncio
async def test_truncation_recovery_no_budget_no_guard() -> None:
    """When per_model_timeout_sec is None, budget guard is skipped entirely."""
    client = _make_client()
    runner = ChatAttemptRunner(client, MagicMock())

    runner._attempt_transport = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_TRUNCATION_OUTCOME, _SUCCESS_OUTCOME]
    )

    state = await runner.run_attempts_for_model(
        **_common_kwargs(),
        per_model_timeout_sec=None,  # No budget — guard must be inactive.
    )

    assert state.terminal_result is not None
    assert runner._attempt_transport.await_count == 2
