"""Unit tests for ``LLMClientFactory``.

These exercise the public dispatching logic without instantiating any real
HTTP client or talking to the network: each provider branch is patched at the
underlying constructor so no API key or live socket is required.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.llm.factory import VALID_PROVIDERS, LLMClientFactory

pytestmark = pytest.mark.no_network


def _stub_config(provider: str = "openrouter") -> Any:
    """Minimal stand-in for ``AppConfig`` with the fields the factory reads."""
    return SimpleNamespace(
        runtime=SimpleNamespace(
            llm_provider=provider,
            request_timeout_sec=30,
            debug_payloads=False,
        ),
        openrouter=SimpleNamespace(
            model="primary",
            fallback_models=(),
            api_key="or-test",
        ),
        openai=SimpleNamespace(
            model="gpt-test",
            fallback_models=(),
            api_key="sk-test",
            organization=None,
            enable_structured_outputs=True,
        ),
        anthropic=SimpleNamespace(
            model="claude-test",
            fallback_models=(),
            api_key="ant-test",
            enable_structured_outputs=True,
        ),
        ollama=SimpleNamespace(
            model="ollama-test",
            fallback_models=(),
            api_key="ol-test",
            base_url="http://ollama:11434/v1",
            enable_structured_outputs=False,
            max_response_size_mb=10,
        ),
    )


def test_valid_providers_constant_exposes_all_four() -> None:
    assert VALID_PROVIDERS == frozenset({"openrouter", "openai", "anthropic", "ollama"})


@pytest.mark.parametrize(
    ("user_provided", "expected_normalized"),
    [
        ("OpenRouter", "openrouter"),
        ("  openai  ", "openai"),
        ("ANTHROPIC", "anthropic"),
        ("Ollama", "ollama"),
    ],
)
def test_create_normalizes_provider_name_before_dispatch(
    user_provided: str, expected_normalized: str
) -> None:
    """``create`` lowercases and strips whitespace so users can be sloppy."""
    cfg = _stub_config()
    sentinel = MagicMock()
    target = f"_create_{expected_normalized}"

    with patch.object(LLMClientFactory, target, return_value=sentinel) as mock_branch:
        result = LLMClientFactory.create(user_provided, cfg)

    assert result is sentinel
    mock_branch.assert_called_once()


def test_create_rejects_unknown_provider_with_helpful_message() -> None:
    with pytest.raises(ValueError, match="Invalid LLM provider"):
        LLMClientFactory.create("totally-fake", _stub_config())


def test_create_rejects_empty_provider_string() -> None:
    with pytest.raises(ValueError):
        LLMClientFactory.create("   ", _stub_config())


def test_create_dispatches_to_openrouter_constructor() -> None:
    cfg = _stub_config(provider="openrouter")
    with patch(
        "app.adapters.openrouter.openrouter_client.OpenRouterClient.from_config",
        return_value=MagicMock(),
    ) as mock_from_config:
        LLMClientFactory.create("openrouter", cfg)

    mock_from_config.assert_called_once()


def test_create_dispatches_to_openai_client() -> None:
    cfg = _stub_config(provider="openai")
    with patch("app.adapters.llm.openai.OpenAIClient") as mock_client:
        LLMClientFactory.create("openai", cfg)

    mock_client.assert_called_once()
    kwargs = mock_client.call_args.kwargs
    assert kwargs["api_key"] == "sk-test"
    assert kwargs["model"] == "gpt-test"


def test_create_dispatches_to_anthropic_client() -> None:
    cfg = _stub_config(provider="anthropic")
    with patch("app.adapters.llm.anthropic.AnthropicClient") as mock_client:
        LLMClientFactory.create("anthropic", cfg)

    mock_client.assert_called_once()
    kwargs = mock_client.call_args.kwargs
    assert kwargs["api_key"] == "ant-test"
    assert kwargs["model"] == "claude-test"


def test_create_dispatches_to_ollama_via_openai_compat_client() -> None:
    """Ollama is wired through the OpenAI client with provider_name='ollama'."""
    cfg = _stub_config(provider="ollama")
    with patch("app.adapters.llm.openai.OpenAIClient") as mock_client:
        LLMClientFactory.create("ollama", cfg)

    mock_client.assert_called_once()
    kwargs = mock_client.call_args.kwargs
    assert kwargs["provider_name"] == "ollama"
    assert kwargs["base_url"] == "http://ollama:11434/v1"


def test_get_provider_from_config_reads_runtime_field() -> None:
    cfg = _stub_config(provider="anthropic")
    assert LLMClientFactory.get_provider_from_config(cfg) == "anthropic"


def test_get_provider_from_config_defaults_to_openrouter_when_unset() -> None:
    cfg = SimpleNamespace(runtime=SimpleNamespace())
    assert LLMClientFactory.get_provider_from_config(cfg) == "openrouter"  # type: ignore[arg-type]


def test_create_from_config_uses_provider_from_config() -> None:
    cfg = _stub_config(provider="anthropic")
    sentinel = MagicMock()
    with patch.object(LLMClientFactory, "_create_anthropic", return_value=sentinel) as mock_branch:
        result = LLMClientFactory.create_from_config(cfg)

    assert result is sentinel
    mock_branch.assert_called_once()


def test_create_forwards_circuit_breaker_and_audit_to_branch() -> None:
    cfg = _stub_config(provider="openrouter")
    audit = MagicMock()
    cb = MagicMock()

    with patch(
        "app.adapters.openrouter.openrouter_client.OpenRouterClient.from_config",
        return_value=MagicMock(),
    ) as mock_from_config:
        LLMClientFactory.create("openrouter", cfg, circuit_breaker=cb, audit=audit)

    # The branch should receive the same circuit_breaker / audit references
    kwargs = mock_from_config.call_args.kwargs
    assert kwargs["circuit_breaker"] is cb
    assert kwargs["audit"] is audit
