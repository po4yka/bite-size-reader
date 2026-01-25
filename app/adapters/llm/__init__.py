"""Multi-provider LLM client abstraction layer.

This module provides a unified interface for interacting with various LLM providers
(OpenRouter, OpenAI, Anthropic) through a common protocol.

Key components:
- LLMClientProtocol: Abstract interface for all LLM clients
- LLMClientFactory: Factory for creating provider-specific clients
- BaseLLMClient: Shared functionality (HTTP pooling, retry, circuit breaker)
- OpenAIClient: Direct OpenAI API client
- AnthropicClient: Direct Anthropic API client
"""

from app.adapters.llm.anthropic import AnthropicClient
from app.adapters.llm.base_client import BaseLLMClient, asyncio_sleep_backoff
from app.adapters.llm.factory import LLMClientFactory
from app.adapters.llm.openai import OpenAIClient
from app.adapters.llm.protocol import LLMClientProtocol

__all__ = [
    "AnthropicClient",
    "BaseLLMClient",
    "LLMClientFactory",
    "LLMClientProtocol",
    "OpenAIClient",
    "asyncio_sleep_backoff",
]
