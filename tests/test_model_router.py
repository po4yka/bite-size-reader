"""Tests for model routing resolution."""

from __future__ import annotations

import pytest

from app.config.llm import ModelRoutingConfig, OpenRouterConfig
from app.core.content_classifier import ContentTier
from app.core.model_router import resolve_fallback_models, resolve_model_for_content


@pytest.fixture
def routing_config() -> ModelRoutingConfig:
    return ModelRoutingConfig(
        enabled=True,
        default_model="anthropic/claude-sonnet-4.6",
        technical_model="google/gemini-3.1-pro-preview",
        sociopolitical_model="x-ai/grok-4.20-beta",
        long_context_model="anthropic/claude-sonnet-4.6",
        long_context_threshold=50000,
    )


@pytest.fixture
def openrouter_config() -> OpenRouterConfig:
    return OpenRouterConfig(
        api_key="test-key",
        model="deepseek/deepseek-v3.2",
    )


class TestResolveModelForContent:
    def test_default_tier(
        self,
        routing_config: ModelRoutingConfig,
        openrouter_config: OpenRouterConfig,
    ) -> None:
        result = resolve_model_for_content(
            tier=ContentTier.DEFAULT,
            content_length=1000,
            has_images=False,
            routing_config=routing_config,
            openrouter_config=openrouter_config,
        )
        assert result == "anthropic/claude-sonnet-4.6"

    def test_technical_tier(
        self,
        routing_config: ModelRoutingConfig,
        openrouter_config: OpenRouterConfig,
    ) -> None:
        result = resolve_model_for_content(
            tier=ContentTier.TECHNICAL,
            content_length=1000,
            has_images=False,
            routing_config=routing_config,
            openrouter_config=openrouter_config,
        )
        assert result == "google/gemini-3.1-pro-preview"

    def test_sociopolitical_tier(
        self,
        routing_config: ModelRoutingConfig,
        openrouter_config: OpenRouterConfig,
    ) -> None:
        result = resolve_model_for_content(
            tier=ContentTier.SOCIOPOLITICAL,
            content_length=1000,
            has_images=False,
            routing_config=routing_config,
            openrouter_config=openrouter_config,
        )
        assert result == "x-ai/grok-4.20-beta"

    def test_long_context_overrides_tier(
        self,
        routing_config: ModelRoutingConfig,
        openrouter_config: OpenRouterConfig,
    ) -> None:
        """Long context should override content tier selection."""
        result = resolve_model_for_content(
            tier=ContentTier.TECHNICAL,
            content_length=60000,
            has_images=False,
            routing_config=routing_config,
            openrouter_config=openrouter_config,
        )
        assert result == "anthropic/claude-sonnet-4.6"

    def test_below_long_context_threshold(
        self,
        routing_config: ModelRoutingConfig,
        openrouter_config: OpenRouterConfig,
    ) -> None:
        """Content below threshold should use tier model, not long context."""
        result = resolve_model_for_content(
            tier=ContentTier.TECHNICAL,
            content_length=49999,
            has_images=False,
            routing_config=routing_config,
            openrouter_config=openrouter_config,
        )
        assert result == "google/gemini-3.1-pro-preview"


class TestResolveFallbackModels:
    def test_returns_configured_fallbacks(self) -> None:
        config = ModelRoutingConfig(
            enabled=True,
            fallback_models=(
                "deepseek/deepseek-v3.2",
                "anthropic/claude-opus-4.6",
                "openai/gpt-5.4",
            ),
        )
        result = resolve_fallback_models(config)
        assert result == (
            "deepseek/deepseek-v3.2",
            "anthropic/claude-opus-4.6",
            "openai/gpt-5.4",
        )
