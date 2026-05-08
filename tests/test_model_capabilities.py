"""Tests for model capabilities detection."""

from __future__ import annotations

import pytest

from app.adapters.openrouter.model_capabilities import ModelCapabilities


@pytest.fixture
def capabilities() -> ModelCapabilities:
    return ModelCapabilities(api_key="test-key", base_url="https://openrouter.ai/api/v1")


class TestIsReasoningHeavyModel:
    """Verify anchored regex detection avoids false positives and catches known patterns."""

    @pytest.mark.parametrize(
        "model",
        [
            "openai/o1",
            "openai/o1-mini",
            "openai/o3-mini",
            "openai/o4-mini",
            "deepseek/deepseek-r1",
            "deepseek/deepseek-r1-0528",
            "qwen/qwen3-next-80b-a3b-thinking",
            "some/reasoning-model",
        ],
    )
    def test_detected_as_reasoning(self, capabilities: ModelCapabilities, model: str) -> None:
        assert capabilities.is_reasoning_heavy_model(model) is True, (
            f"Expected {model!r} to be classified as reasoning-heavy"
        )

    @pytest.mark.parametrize(
        "model",
        [
            "mistral/medio1",  # contains "o1" as substring — must NOT match
            "deepseek/deepseek-v4-flash",
            "deepseek/deepseek-v4-pro",
            "qwen/qwen3.6-flash",
            "minimax/minimax-m2",
            "moonshotai/kimi-k2",
            "x-ai/grok-4.20-beta",
            "anthropic/claude-opus-4.6",
        ],
    )
    def test_not_detected_as_reasoning(self, capabilities: ModelCapabilities, model: str) -> None:
        assert capabilities.is_reasoning_heavy_model(model) is False, (
            f"Expected {model!r} NOT to be classified as reasoning-heavy"
        )
