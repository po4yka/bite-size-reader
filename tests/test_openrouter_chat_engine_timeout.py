"""Tests for OpenRouterChatEngine timeout exhaustion telemetry.

Regression guard for incident 640f444f2bcc: when every model in the fallback
chain times out, the exhausted LLMCallResult must name the last tried model
(not None, which the persistence layer coerces to the primary model name,
producing misleading `llm_calls.model` rows during post-mortem analysis).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.adapters.openrouter.chat_engine import OpenRouterChatEngine
from app.adapters.openrouter.openrouter_client import OpenRouterClient, OpenRouterClientConfig
from app.core.call_status import CallStatus


def _make_client() -> OpenRouterClient:
    return OpenRouterClient(
        api_key="sk-or-test-key",
        model="primary/m0",
        fallback_models=("fallback/m1", "fallback/m2"),
        config=OpenRouterClientConfig(max_retries=1),
    )


@pytest.mark.asyncio
async def test_chat_engine_all_models_timeout_reports_last_tried_model() -> None:
    client = _make_client()
    engine = OpenRouterChatEngine(client)

    @asynccontextmanager
    async def _fake_request_context() -> Any:
        yield MagicMock()

    client._request_context = _fake_request_context  # type: ignore[method-assign]

    async def _sleep_past_timeout(**kwargs: Any) -> Any:
        await asyncio.sleep(1.0)
        return MagicMock()

    engine._attempt_runner.run_attempts_for_model = _sleep_past_timeout  # type: ignore[method-assign]

    result = await engine.chat(
        messages=[{"role": "user", "content": "hi"}],
        response_format=None,
        model_override="primary/m0",
        fallback_models_override=("fallback/m1", "fallback/m2"),
        per_model_timeout_sec=0.05,
    )

    assert result.status == CallStatus.ERROR
    assert result.model == "fallback/m2", (
        f"Expected last tried model in the chain, got {result.model!r}. "
        "Regression of incident 640f444f2bcc: exhausted chain reported "
        "model=None and persistence coerced it to the primary."
    )
    assert result.error_text is not None
    assert "fallback/m2" in result.error_text
    assert "timed out" in result.error_text
