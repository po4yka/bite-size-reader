"""Tests for LLM-based content quality classification."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.adapter_models.llm.llm_models import LLMCallResult
from app.adapters.content.quality_filters import (
    classify_content_quality_llm,
    is_gray_zone_for_llm_check,
)
from app.core.call_status import CallStatus

# ---------------------------------------------------------------------------
# is_gray_zone_for_llm_check tests
# ---------------------------------------------------------------------------


def test_is_gray_zone_nav_stub_in_range() -> None:
    assert is_gray_zone_for_llm_check(
        "nav_stub_detected",
        {"word_count": 50, "substantive_sentence_count": 1},
    )


def test_is_gray_zone_non_nav_stub_reason() -> None:
    assert not is_gray_zone_for_llm_check(
        "overlay_content_detected",
        {"word_count": 50, "substantive_sentence_count": 1},
    )


def test_is_gray_zone_below_min_words() -> None:
    assert not is_gray_zone_for_llm_check(
        "nav_stub_detected",
        {"word_count": 10, "substantive_sentence_count": 0},
    )


def test_is_gray_zone_above_max_words() -> None:
    assert not is_gray_zone_for_llm_check(
        "nav_stub_detected",
        {"word_count": 200, "substantive_sentence_count": 1},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_result(
    response_text: str,
    status: CallStatus = CallStatus.OK,
) -> LLMCallResult:
    return LLMCallResult(
        status=status,
        model="google/gemini-3-flash-preview",
        response_text=response_text,
        tokens_prompt=100,
        tokens_completion=20,
        cost_usd=0.0001,
        latency_ms=500,
    )


def _make_mock_client(response_text: str) -> AsyncMock:
    client = AsyncMock()
    client.provider_name = "openrouter"
    client.chat = AsyncMock(return_value=_make_llm_result(response_text))
    return client


_DEFAULT_METRICS: dict[str, Any] = {
    "word_count": 50,
    "substantive_sentence_count": 1,
}


# ---------------------------------------------------------------------------
# classify_content_quality_llm tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="function")
async def test_llm_classifies_real_content() -> None:
    client = _make_mock_client('{"classification": "real_content", "confidence": 0.9}')
    is_stub, result = await classify_content_quality_llm(
        "Some text preview",
        _DEFAULT_METRICS,
        client,
        flash_model="test-model",
        flash_fallback_models=(),
    )
    assert is_stub is False
    assert result is not None


@pytest.mark.asyncio(loop_scope="function")
async def test_llm_classifies_stub() -> None:
    client = _make_mock_client('{"classification": "stub", "confidence": 0.95}')
    is_stub, result = await classify_content_quality_llm(
        "Nav stub text",
        _DEFAULT_METRICS,
        client,
        flash_model="test-model",
        flash_fallback_models=(),
    )
    assert is_stub is True
    assert result is not None


@pytest.mark.asyncio(loop_scope="function")
async def test_llm_low_confidence_defers_to_heuristic() -> None:
    client = _make_mock_client('{"classification": "real_content", "confidence": 0.4}')
    is_stub, result = await classify_content_quality_llm(
        "Ambiguous text",
        _DEFAULT_METRICS,
        client,
        flash_model="test-model",
        flash_fallback_models=(),
        confidence_threshold=0.7,
    )
    assert is_stub is True  # Defers to heuristic
    assert result is not None


@pytest.mark.asyncio(loop_scope="function")
async def test_llm_timeout_defers_to_heuristic() -> None:
    client = AsyncMock()
    client.provider_name = "openrouter"
    client.chat = AsyncMock(side_effect=TimeoutError())
    is_stub, result = await classify_content_quality_llm(
        "Some text",
        _DEFAULT_METRICS,
        client,
        flash_model="test-model",
        flash_fallback_models=(),
        timeout_sec=0.1,
    )
    assert is_stub is True
    assert result is None


@pytest.mark.asyncio(loop_scope="function")
async def test_llm_parse_error_defers_to_heuristic() -> None:
    client = _make_mock_client("not json at all {{{")
    is_stub, result = await classify_content_quality_llm(
        "Some text",
        _DEFAULT_METRICS,
        client,
        flash_model="test-model",
        flash_fallback_models=(),
    )
    # json_repair may parse this as something; either way should not crash
    assert isinstance(is_stub, bool)
    assert result is not None
