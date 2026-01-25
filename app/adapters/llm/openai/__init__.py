"""OpenAI LLM client implementation.

This module provides a direct OpenAI API client that implements the LLMClientProtocol,
allowing it to be used interchangeably with other LLM providers.
"""

from app.adapters.llm.openai.client import OpenAIClient

__all__ = ["OpenAIClient"]
