"""Anthropic LLM client implementation.

This module provides a direct Anthropic API client that implements the LLMClientProtocol,
allowing it to be used interchangeably with other LLM providers.
"""

from app.adapters.llm.anthropic.client import AnthropicClient

__all__ = ["AnthropicClient"]
