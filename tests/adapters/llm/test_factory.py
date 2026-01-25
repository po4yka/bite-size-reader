"""Tests for LLM client factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.adapters.llm.factory import VALID_PROVIDERS, LLMClientFactory


class TestLLMClientFactory:
    """Tests for LLMClientFactory."""

    def test_valid_providers_constant(self) -> None:
        """VALID_PROVIDERS should contain expected values."""
        assert frozenset({"openrouter", "openai", "anthropic"}) == VALID_PROVIDERS

    def test_invalid_provider_raises_value_error(self) -> None:
        """Invalid provider should raise ValueError."""
        mock_config = MagicMock()
        with pytest.raises(ValueError, match="Invalid LLM provider"):
            LLMClientFactory.create("invalid", mock_config)

    def test_provider_name_is_case_insensitive(self) -> None:
        """Provider name should be case insensitive."""
        mock_config = MagicMock()
        mock_config.runtime.llm_provider = "openrouter"
        mock_config.openrouter.api_key = "test-key-valid-12345"
        mock_config.openrouter.model = "test-model"
        mock_config.openrouter.fallback_models = []
        mock_config.openrouter.http_referer = None
        mock_config.openrouter.x_title = None
        mock_config.runtime.request_timeout_sec = 60
        mock_config.runtime.debug_payloads = False
        mock_config.openrouter.provider_order = []
        mock_config.openrouter.enable_stats = False
        mock_config.runtime.log_truncate_length = 1000
        mock_config.openrouter.enable_structured_outputs = False
        mock_config.openrouter.structured_output_mode = "json_object"
        mock_config.openrouter.require_parameters = False
        mock_config.openrouter.auto_fallback_structured = False
        mock_config.openrouter.max_response_size_mb = 10

        # Should not raise for uppercase
        with patch("app.adapters.llm.factory.LLMClientFactory._create_openrouter") as mock_create:
            mock_create.return_value = MagicMock()
            client = LLMClientFactory.create("OPENROUTER", mock_config)
            assert client is not None

    def test_get_provider_from_config(self) -> None:
        """Should return provider from config.runtime.llm_provider."""
        mock_config = MagicMock()
        mock_config.runtime.llm_provider = "anthropic"

        provider = LLMClientFactory.get_provider_from_config(mock_config)
        assert provider == "anthropic"

    def test_get_provider_from_config_defaults_to_openrouter(self) -> None:
        """Should default to openrouter if not configured."""
        mock_config = MagicMock()
        del mock_config.runtime.llm_provider  # Remove the attribute

        provider = LLMClientFactory.get_provider_from_config(mock_config)
        assert provider == "openrouter"


class TestRequestBuilders:
    """Tests for provider-specific request builders."""

    def test_openai_request_builder_headers(self) -> None:
        """OpenAI request builder should produce correct headers."""
        from app.adapters.llm.openai.request_builder import OpenAIRequestBuilder

        builder = OpenAIRequestBuilder(api_key="test-key")
        headers = builder.build_headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test-key"
        assert headers["Content-Type"] == "application/json"

    def test_anthropic_request_builder_headers(self) -> None:
        """Anthropic request builder should produce correct headers."""
        from app.adapters.llm.anthropic.request_builder import AnthropicRequestBuilder

        builder = AnthropicRequestBuilder(api_key="test-key")
        headers = builder.build_headers()

        assert "x-api-key" in headers
        assert headers["x-api-key"] == "test-key"
        assert "anthropic-version" in headers

    def test_anthropic_extracts_system_message(self) -> None:
        """Anthropic builder should extract system message to top level."""
        from app.adapters.llm.anthropic.request_builder import AnthropicRequestBuilder

        builder = AnthropicRequestBuilder(api_key="test-key")
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello!"},
        ]

        body = builder.build_request_body(
            model="claude-3-sonnet",
            messages=messages,
        )

        # System should be extracted to top level
        assert "system" in body
        assert body["system"] == "You are helpful."

        # Messages should only have user message
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "user"


class TestPricingCalculation:
    """Tests for provider pricing calculations."""

    def test_openai_pricing_calculation(self) -> None:
        """OpenAI pricing should calculate correctly."""
        from app.adapters.llm.openai.request_builder import calculate_cost

        # gpt-4o: $2.50/1M input, $10.00/1M output
        cost = calculate_cost("gpt-4o", prompt_tokens=1000, completion_tokens=500)
        expected = (1000 / 1_000_000) * 2.50 + (500 / 1_000_000) * 10.00
        assert cost == pytest.approx(expected)

    def test_anthropic_pricing_calculation(self) -> None:
        """Anthropic pricing should calculate correctly."""
        from app.adapters.llm.anthropic.request_builder import calculate_cost

        # claude-sonnet-4-5: $3.00/1M input, $15.00/1M output
        cost = calculate_cost(
            "claude-sonnet-4-5-20250929", prompt_tokens=1000, completion_tokens=500
        )
        expected = (1000 / 1_000_000) * 3.00 + (500 / 1_000_000) * 15.00
        assert cost == pytest.approx(expected)

    def test_unknown_model_returns_none(self) -> None:
        """Unknown model should return None for cost."""
        from app.adapters.llm.openai.request_builder import calculate_cost

        cost = calculate_cost("unknown-model-xyz", prompt_tokens=1000, completion_tokens=500)
        assert cost is None
