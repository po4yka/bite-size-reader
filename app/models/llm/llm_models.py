"""Data models for LLM interactions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LLMCallResult:
    """Result of an LLM API call with comprehensive metadata."""

    status: str
    model: str | None
    response_text: str | None
    response_json: dict | None
    tokens_prompt: int | None
    tokens_completion: int | None
    cost_usd: float | None
    latency_ms: int | None
    error_text: str | None
    request_headers: dict | None = None
    request_messages: list[dict] | None = None
    endpoint: str | None = "/api/v1/chat/completions"
    structured_output_used: bool = False
    structured_output_mode: str | None = None
    error_context: dict[str, Any] | None = None


@dataclass
class ChatRequest:
    """Request parameters for chat completions."""

    messages: list[dict[str, str]]
    temperature: float = 0.2
    max_tokens: int | None = None
    top_p: float | None = None
    stream: bool = False
    request_id: int | None = None
    response_format: dict[str, Any] | None = None
    model_override: str | None = None
