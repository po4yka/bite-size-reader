"""LLM client protocol defining the common interface for all providers.

This module defines the abstract protocol that all LLM clients must implement,
enabling polymorphic usage across OpenRouter, OpenAI, and Anthropic providers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.models.llm.llm_models import LLMCallResult


@runtime_checkable
class LLMClientProtocol(Protocol):
    """Protocol defining the interface for LLM clients.

    All LLM provider implementations (OpenRouter, OpenAI, Anthropic) must
    implement this protocol to be used interchangeably in the application.

    The protocol focuses on the core chat completions functionality that
    all providers support, abstracting away provider-specific details.
    """

    @property
    def provider_name(self) -> str:
        """Return the name of the LLM provider.

        Returns:
            Provider identifier string (e.g., "openrouter", "openai", "anthropic")
        """
        ...

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stream: bool = False,
        request_id: int | None = None,
        response_format: dict[str, Any] | None = None,
        model_override: str | None = None,
    ) -> LLMCallResult:
        """Send a chat completion request to the LLM provider.

        Args:
            messages: List of message dictionaries with 'role' and 'content' keys.
                     Roles are typically 'system', 'user', or 'assistant'.
            temperature: Sampling temperature (0.0 to 2.0). Lower values make
                        output more deterministic.
            max_tokens: Maximum number of tokens to generate. If None, uses
                       provider defaults.
            top_p: Nucleus sampling parameter (0.0 to 1.0). If None, uses
                  provider defaults.
            stream: Whether to stream the response. Currently not implemented
                   for most providers.
            request_id: Optional internal request ID for tracing and persistence.
            response_format: Optional structured output format specification.
                           Provider-specific handling applies.
            model_override: Optional model name to use instead of the default.

        Returns:
            LLMCallResult containing the response text, token usage, cost,
            latency, and any error information.

        Raises:
            RuntimeError: If the client has been closed.
            ValidationError: If the request parameters are invalid.
        """
        ...

    async def aclose(self) -> None:
        """Close the client and release any resources.

        This method should be called when the client is no longer needed
        to properly clean up HTTP connections and other resources.

        After calling aclose(), the client should not be used for further
        requests. Calling chat() after aclose() should raise RuntimeError.
        """
        ...
