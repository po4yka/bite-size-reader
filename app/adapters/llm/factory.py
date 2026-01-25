"""LLM client factory for creating provider-specific clients.

This module provides a factory for creating LLM clients based on the configured
provider (openrouter, openai, anthropic).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.llm.protocol import LLMClientProtocol
    from app.config import AppConfig
    from app.utils.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

# Valid provider names
VALID_PROVIDERS = frozenset({"openrouter", "openai", "anthropic"})


class LLMClientFactory:
    """Factory for creating LLM clients based on provider configuration.

    This factory abstracts the creation of provider-specific clients,
    allowing the application to switch between providers via configuration.

    Usage:
        client = LLMClientFactory.create("openrouter", config)
        result = await client.chat(messages)
    """

    @staticmethod
    def create(
        provider: str,
        config: AppConfig,
        *,
        circuit_breaker: CircuitBreaker | None = None,
        audit: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> LLMClientProtocol:
        """Create an LLM client for the specified provider.

        Args:
            provider: Provider name ("openrouter", "openai", "anthropic").
            config: Application configuration.
            circuit_breaker: Optional circuit breaker for fault tolerance.
            audit: Optional audit callback function.

        Returns:
            LLM client implementing LLMClientProtocol.

        Raises:
            ValueError: If the provider is not supported.
        """
        provider = provider.lower().strip()

        if provider not in VALID_PROVIDERS:
            msg = f"Invalid LLM provider: {provider}. Must be one of {sorted(VALID_PROVIDERS)}"
            raise ValueError(msg)

        logger.info(
            "llm_client_factory_creating",
            extra={"provider": provider},
        )

        if provider == "openrouter":
            return LLMClientFactory._create_openrouter(config, circuit_breaker, audit)
        if provider == "openai":
            return LLMClientFactory._create_openai(config, circuit_breaker, audit)
        if provider == "anthropic":
            return LLMClientFactory._create_anthropic(config, circuit_breaker, audit)
        # Should never reach here due to validation above
        msg = f"Unhandled provider: {provider}"
        raise ValueError(msg)

    @staticmethod
    def _create_openrouter(
        config: AppConfig,
        circuit_breaker: CircuitBreaker | None,
        audit: Callable[[str, str, dict[str, Any]], None] | None,
    ) -> LLMClientProtocol:
        """Create an OpenRouter client."""
        from app.adapters.openrouter.openrouter_client import OpenRouterClient

        return OpenRouterClient(
            api_key=config.openrouter.api_key,
            model=config.openrouter.model,
            fallback_models=list(config.openrouter.fallback_models),
            http_referer=config.openrouter.http_referer,
            x_title=config.openrouter.x_title,
            timeout_sec=config.runtime.request_timeout_sec,
            audit=audit,
            debug_payloads=config.runtime.debug_payloads,
            provider_order=list(config.openrouter.provider_order),
            enable_stats=config.openrouter.enable_stats,
            log_truncate_length=config.runtime.log_truncate_length,
            enable_structured_outputs=config.openrouter.enable_structured_outputs,
            structured_output_mode=config.openrouter.structured_output_mode,
            require_parameters=config.openrouter.require_parameters,
            auto_fallback_structured=config.openrouter.auto_fallback_structured,
            max_response_size_mb=config.openrouter.max_response_size_mb,
            circuit_breaker=circuit_breaker,
        )

    @staticmethod
    def _create_openai(
        config: AppConfig,
        circuit_breaker: CircuitBreaker | None,
        audit: Callable[[str, str, dict[str, Any]], None] | None,
    ) -> LLMClientProtocol:
        """Create an OpenAI client."""
        from app.adapters.llm.openai import OpenAIClient

        openai_config = config.openai

        return OpenAIClient(
            api_key=openai_config.api_key,
            model=openai_config.model,
            fallback_models=list(openai_config.fallback_models),
            organization=openai_config.organization,
            timeout_sec=config.runtime.request_timeout_sec,
            debug_payloads=config.runtime.debug_payloads,
            enable_structured_outputs=openai_config.enable_structured_outputs,
            circuit_breaker=circuit_breaker,
            audit=audit,
        )

    @staticmethod
    def _create_anthropic(
        config: AppConfig,
        circuit_breaker: CircuitBreaker | None,
        audit: Callable[[str, str, dict[str, Any]], None] | None,
    ) -> LLMClientProtocol:
        """Create an Anthropic client."""
        from app.adapters.llm.anthropic import AnthropicClient

        anthropic_config = config.anthropic

        return AnthropicClient(
            api_key=anthropic_config.api_key,
            model=anthropic_config.model,
            fallback_models=list(anthropic_config.fallback_models),
            timeout_sec=config.runtime.request_timeout_sec,
            debug_payloads=config.runtime.debug_payloads,
            enable_structured_outputs=anthropic_config.enable_structured_outputs,
            circuit_breaker=circuit_breaker,
            audit=audit,
        )

    @staticmethod
    def get_provider_from_config(config: AppConfig) -> str:
        """Get the LLM provider from configuration.

        Args:
            config: Application configuration.

        Returns:
            Provider name string.
        """
        return getattr(config.runtime, "llm_provider", "openrouter")

    @staticmethod
    def create_from_config(
        config: AppConfig,
        *,
        circuit_breaker: CircuitBreaker | None = None,
        audit: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> LLMClientProtocol:
        """Create an LLM client using the provider specified in config.

        This is a convenience method that reads the provider from config
        and creates the appropriate client.

        Args:
            config: Application configuration.
            circuit_breaker: Optional circuit breaker for fault tolerance.
            audit: Optional audit callback function.

        Returns:
            LLM client implementing LLMClientProtocol.
        """
        provider = LLMClientFactory.get_provider_from_config(config)
        return LLMClientFactory.create(
            provider, config, circuit_breaker=circuit_breaker, audit=audit
        )
