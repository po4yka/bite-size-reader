"""Unit tests for ``app.adapters.openrouter.model_capabilities``.

These cover the pure-logic provider detection and capability helpers without
hitting the OpenRouter HTTP API — the network-touching ``ensure_*``/``get_*``
methods are exercised via mocked ``httpx.AsyncClient`` responses.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.openrouter.model_capabilities import (
    AUTOMATIC_CACHING_PROVIDERS,
    EXPLICIT_CACHING_PROVIDERS,
    ModelCapabilities,
    detect_provider,
    get_caching_info,
    supports_automatic_caching,
    supports_explicit_caching,
)

pytestmark = pytest.mark.no_network


# ---------------------------------------------------------------------------
# detect_provider
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("anthropic/claude-3-opus", "anthropic"),
        ("claude-3-haiku", "anthropic"),
        ("google/gemini-2.5-pro", "google"),
        ("gemini-1.5-pro", "google"),
        ("openai/gpt-4o", "openai"),
        ("gpt-4-turbo", "openai"),
        ("deepseek/deepseek-v4-flash", "deepseek"),
        ("qwen/qwen3.5-plus-02-15", "qwen"),
        ("minimax/minimax-m2", "minimax"),
        ("moonshotai/kimi-k2", "moonshotai"),
        ("kimi-k2.5", "moonshotai"),
        ("meta-llama/llama-3.3-70b", "meta"),
        ("mistral/mixtral-8x22b", "mistral"),
        ("cohere/command-r-plus", "cohere"),
        ("ANTHROPIC/CLAUDE-3-OPUS", "anthropic"),  # case-insensitive
    ],
)
def test_detect_provider_matches_known_prefixes(model: str, expected: str) -> None:
    assert detect_provider(model) == expected


def test_detect_provider_returns_unknown_for_strange_id() -> None:
    assert detect_provider("acme/super-model-9000") == "unknown"


# ---------------------------------------------------------------------------
# caching helpers
# ---------------------------------------------------------------------------


def test_explicit_caching_providers_constant_matches_documented_set() -> None:
    assert frozenset({"anthropic", "google"}) == EXPLICIT_CACHING_PROVIDERS


def test_automatic_caching_providers_constant_matches_documented_set() -> None:
    assert "openai" in AUTOMATIC_CACHING_PROVIDERS
    assert "deepseek" in AUTOMATIC_CACHING_PROVIDERS
    assert "anthropic" not in AUTOMATIC_CACHING_PROVIDERS


@pytest.mark.parametrize("model", ["anthropic/claude-3-opus", "google/gemini-1.5-pro"])
def test_supports_explicit_caching_true_for_explicit_providers(model: str) -> None:
    assert supports_explicit_caching(model) is True


@pytest.mark.parametrize("model", ["openai/gpt-4o", "deepseek/deepseek-v4-flash"])
def test_supports_explicit_caching_false_for_automatic_providers(model: str) -> None:
    assert supports_explicit_caching(model) is False


@pytest.mark.parametrize("model", ["openai/gpt-4o", "deepseek/deepseek-v4-flash", "qwen/qwen3-max"])
def test_supports_automatic_caching_true_for_automatic_providers(model: str) -> None:
    assert supports_automatic_caching(model) is True


def test_supports_automatic_caching_false_for_anthropic() -> None:
    assert supports_automatic_caching("anthropic/claude-3-opus") is False


def test_get_caching_info_for_explicit_provider() -> None:
    info = get_caching_info("anthropic/claude-3-opus")
    assert info["supports_caching"] is True
    assert info["caching_type"] == "explicit"
    assert info["requires_cache_control"] is True
    assert info["provider"] == "anthropic"
    assert "breakpoints" in info["notes"]


def test_get_caching_info_for_automatic_provider() -> None:
    info = get_caching_info("deepseek/deepseek-v4-flash")
    assert info["supports_caching"] is True
    assert info["caching_type"] == "automatic"
    assert info["requires_cache_control"] is False
    assert info["provider"] == "deepseek"


def test_get_caching_info_unknown_provider_returns_unknown_record() -> None:
    info = get_caching_info("foo/bar-1")
    assert info["supports_caching"] is False
    assert info["caching_type"] == "unknown"
    assert info["provider"] == "unknown"


# ---------------------------------------------------------------------------
# ModelCapabilities — reasoning-heavy detection
# ---------------------------------------------------------------------------


def _make_caps() -> ModelCapabilities:
    return ModelCapabilities(
        api_key="sk-test",
        base_url="https://example.invalid/api/v1",
        timeout=5,
    )


@pytest.mark.parametrize(
    "model",
    [
        "openai/o1-preview",
        "openai/o3-mini",
        "deepseek/deepseek-r1",
        "moonshotai/kimi-k2-thinking",
        "google/gemini-2.5-flash-thinking",
        "anthropic/claude-3.5-sonnet-reasoning",
    ],
)
def test_is_reasoning_heavy_model_true_for_anchored_indicators(model: str) -> None:
    assert _make_caps().is_reasoning_heavy_model(model) is True


@pytest.mark.parametrize(
    "model",
    [
        "openai/gpt-4o",  # plain GPT-4o is not a reasoning model
        "mistral/medio1",  # contains "o1" substring but not at a boundary
        "qwen/qwen3-max",
    ],
)
def test_is_reasoning_heavy_model_false_for_non_reasoning_models(model: str) -> None:
    assert _make_caps().is_reasoning_heavy_model(model) is False


# ---------------------------------------------------------------------------
# ModelCapabilities — safe structured fallbacks and supports_structured_outputs
# ---------------------------------------------------------------------------


def test_safe_structured_fallbacks_includes_minimax_first() -> None:
    fallbacks = _make_caps().get_safe_structured_fallbacks()
    assert fallbacks
    assert fallbacks[0] == "minimax/minimax-m2"
    assert "qwen/qwen3.5-plus-02-15" in fallbacks


@pytest.mark.parametrize(
    "model",
    [
        "qwen/qwen3.6-flash",
        "qwen/qwen3.6-plus-04-02",
        "moonshotai/kimi-k2",
        "deepseek/deepseek-v4-flash",
        "minimax/minimax-m2",
    ],
)
def test_supports_structured_outputs_returns_true_for_known_models(model: str) -> None:
    assert _make_caps().supports_structured_outputs(model) is True


def test_supports_structured_outputs_false_for_unknown_model() -> None:
    assert _make_caps().supports_structured_outputs("acme/unknown-2024") is False


def test_supports_structured_outputs_prefers_live_capability_cache() -> None:
    caps = _make_caps()
    caps._structured_supported_models = {"acme/unknown-2024"}
    # When the live-fetched cache is populated, it is authoritative — the
    # known-list fallback is bypassed.
    assert caps.supports_structured_outputs("acme/unknown-2024") is True
    assert caps.supports_structured_outputs("deepseek/deepseek-v4-flash") is False


# ---------------------------------------------------------------------------
# ModelCapabilities — async live-fetch path with mocked HTTP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_structured_supported_models_populates_cache_from_http() -> None:
    """A successful /models response should populate the structured-models cache."""
    caps = _make_caps()
    payload = {
        "data": [
            {"id": "openai/gpt-4o", "supported_parameters": ["response_format"]},
            {"id": "qwen/qwen3-max", "supported_parameters": ["structured_outputs"]},
            {"id": "no-support/model", "supported_parameters": []},
        ]
    }
    response = MagicMock()
    response.status_code = 200
    response.json = MagicMock(return_value=payload)
    response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await caps.ensure_structured_supported_models()

    # Both response_format and structured_outputs flags should mark a model as supported.
    assert caps._structured_supported_models is not None
    assert "openai/gpt-4o" in caps._structured_supported_models
    assert "qwen/qwen3-max" in caps._structured_supported_models


@pytest.mark.asyncio
async def test_ensure_structured_supported_models_handles_http_error() -> None:
    """An HTTP failure must not propagate — it just leaves the cache empty."""
    caps = _make_caps()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=RuntimeError("network down"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        await caps.ensure_structured_supported_models()
        # No exception, but cache stays None on transient errors.
