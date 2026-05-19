"""Unit tests for ``OpenRouterClient`` construction, configuration, and aclose.

These exercise the public surface that is reachable without spinning up an
event loop or hitting the network — `__init__`, `from_config`, the
`provider_name`/`circuit_breaker` properties, `get_circuit_breaker_stats`, and
`aclose` behaviour with mocked HTTP clients.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.adapters.openrouter.openrouter_client import (
    OpenRouterClient,
    OpenRouterClientConfig,
)

pytestmark = pytest.mark.no_network


_VALID_KEY = "sk-or-v1-test-key-that-passes-validation-1234567890"


def _make_client(
    *,
    api_key: str = _VALID_KEY,
    model: str = "qwen/qwen3-max",
    config: OpenRouterClientConfig | None = None,
    fallback_models: tuple[str, ...] = (),
    circuit_breaker: Any = None,
    audit: Any = None,
) -> OpenRouterClient:
    return OpenRouterClient(
        api_key=api_key,
        config=config,
        model=model,
        fallback_models=fallback_models,
        audit=audit,
        circuit_breaker=circuit_breaker,
    )


# ---------------------------------------------------------------------------
# OpenRouterClientConfig — dataclass defaults
# ---------------------------------------------------------------------------


def test_client_config_default_values_are_documented_defaults() -> None:
    cfg = OpenRouterClientConfig()
    assert cfg.timeout_sec == 60
    assert cfg.max_retries == 3
    assert cfg.backoff_base == 0.5
    assert cfg.enable_structured_outputs is True
    assert cfg.structured_output_mode == "json_schema"
    assert cfg.auto_fallback_structured is True
    assert cfg.max_response_size_mb == 10
    assert cfg.transport_retry_max_attempts == 3


# ---------------------------------------------------------------------------
# __init__ — basic construction
# ---------------------------------------------------------------------------


def test_construct_with_minimal_args_succeeds() -> None:
    client = _make_client()
    assert client.provider_name == "openrouter"
    assert client._model == "qwen/qwen3-max"
    assert client._closed is False


def test_construct_records_fallback_models_in_order() -> None:
    client = _make_client(fallback_models=("a/m1", "b/m2", "c/m3"))
    assert list(client._fallback_models) == ["a/m1", "b/m2", "c/m3"]


def test_construct_rejects_short_api_key() -> None:
    from app.adapters.openrouter.exceptions import ConfigurationError

    with pytest.raises(ConfigurationError):
        _make_client(api_key="short")


def test_construct_rejects_empty_model() -> None:
    from app.adapters.openrouter.exceptions import ConfigurationError

    with pytest.raises(ConfigurationError):
        _make_client(model="")


def test_construct_accepts_custom_config_block() -> None:
    cfg = OpenRouterClientConfig(timeout_sec=15, max_retries=5)
    client = _make_client(config=cfg)
    # Stored on the client for downstream consumers.
    assert client._timeout.read == 15  # httpx.Timeout(read=...)
    # error_handler initialized with the config's max_retries.
    assert client.error_handler._max_retries == 5


# ---------------------------------------------------------------------------
# from_config — translates AppConfig into a client
# ---------------------------------------------------------------------------


def _stub_app_config() -> Any:
    return SimpleNamespace(
        openrouter=SimpleNamespace(
            api_key=_VALID_KEY,
            model="qwen/qwen3-max",
            fallback_models=("a/m1",),
            http_referer=None,
            x_title=None,
            provider_order=(),
            enable_stats=False,
            enable_structured_outputs=True,
            structured_output_mode="json_schema",
            require_parameters=True,
            auto_fallback_structured=True,
            max_response_size_mb=10,
            enable_prompt_caching=False,
            prompt_cache_ttl="ephemeral",
            prompt_cache_ttl_anthropic="1h",
            cache_system_prompt=False,
            cache_large_content_threshold=4096,
            transport_retry_max_attempts=3,
            transport_retry_min_wait_sec=0.5,
            transport_retry_max_wait_sec=5.0,
        ),
        runtime=SimpleNamespace(
            request_timeout_sec=30,
            debug_payloads=False,
            log_truncate_length=500,
        ),
    )


def test_from_config_builds_client_with_extracted_settings() -> None:
    client = OpenRouterClient.from_config(_stub_app_config())
    assert client.provider_name == "openrouter"
    assert client._model == "qwen/qwen3-max"
    assert list(client._fallback_models) == ["a/m1"]
    # request_timeout_sec maps onto the httpx timeout block.
    assert client._timeout.read == 30


def test_from_config_forwards_circuit_breaker_and_audit_callbacks() -> None:
    cb = MagicMock()
    audit_calls: list[tuple[str, str, dict]] = []
    audit = lambda lvl, ev, d: audit_calls.append((lvl, ev, d))  # noqa: E731

    client = OpenRouterClient.from_config(_stub_app_config(), circuit_breaker=cb, audit=audit)
    assert client.circuit_breaker is cb


# ---------------------------------------------------------------------------
# circuit_breaker integration
# ---------------------------------------------------------------------------


def test_get_circuit_breaker_stats_returns_disabled_marker_without_breaker() -> None:
    client = _make_client()
    stats = client.get_circuit_breaker_stats()
    assert stats == {"state": "disabled"}


def test_get_circuit_breaker_stats_delegates_to_global_breaker() -> None:
    cb = MagicMock()
    cb.get_stats = MagicMock(return_value={"state": "closed", "failure_count": 0})
    # Make sure isinstance(cb, PerModelCircuitBreaker) is False.
    from app.utils.circuit_breaker import PerModelCircuitBreaker

    assert not isinstance(cb, PerModelCircuitBreaker)

    client = _make_client(circuit_breaker=cb)
    assert client.get_circuit_breaker_stats() == {"state": "closed", "failure_count": 0}
    cb.get_stats.assert_called_once()


# ---------------------------------------------------------------------------
# aclose — safe to call when client never opened a pool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aclose_is_idempotent_on_a_fresh_client() -> None:
    """aclose must succeed even when no pooled HTTP client was ever created."""
    client = _make_client()
    await client.aclose()
    # Second close must also be safe.
    await client.aclose()


@pytest.mark.asyncio
async def test_async_context_manager_calls_aclose_on_exit() -> None:
    client = _make_client()
    async with client as same:
        assert same is client
    # After __aexit__, _oai_client should be cleared.
    assert client._oai_client is None
