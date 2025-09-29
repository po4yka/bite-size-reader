"""Data models for LLM interactions backed by Pydantic validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class LLMCallResult(BaseModel):
    """Result of an LLM API call with comprehensive metadata."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="High-level result status (ok, error, etc.).")
    model: str | None = Field(default=None, description="Model that produced the response.")
    response_text: str | None = Field(
        default=None, description="Primary text response returned by the provider."
    )
    response_json: dict[str, Any] | None = Field(
        default=None, description="Structured JSON payload returned by the provider."
    )
    openrouter_response_text: str | None = Field(
        default=None, description="Raw OpenRouter response text (pre-parsing)."
    )
    openrouter_response_json: dict[str, Any] | None = Field(
        default=None, description="Raw OpenRouter JSON payload (pre-processing)."
    )
    tokens_prompt: int | None = Field(
        default=None, description="Prompt tokens consumed by the request."
    )
    tokens_completion: int | None = Field(
        default=None, description="Completion tokens produced by the request."
    )
    cost_usd: float | None = Field(default=None, description="Estimated USD cost for the request.")
    latency_ms: int | None = Field(
        default=None, description="Observed latency for the LLM request in milliseconds."
    )
    error_text: str | None = Field(default=None, description="Error message when the call fails.")
    request_headers: dict[str, Any] | None = Field(
        default=None, description="HTTP headers sent with the request."
    )
    request_messages: list[dict[str, Any]] | None = Field(
        default=None, description="Messages payload submitted to the chat endpoint."
    )
    endpoint: str | None = Field(
        default="/api/v1/chat/completions",
        description="Endpoint used for the LLM call.",
    )
    structured_output_used: bool = Field(
        default=False, description="Whether structured outputs were requested."
    )
    structured_output_mode: str | None = Field(
        default=None, description="Structured output mode requested (if any)."
    )
    error_context: dict[str, Any] | None = Field(
        default=None, description="Additional context about encountered errors."
    )


class ChatRequest(BaseModel):
    """Request parameters for chat completions."""

    model_config = ConfigDict(extra="forbid")

    messages: list[dict[str, str]] = Field(
        description="Conversation messages to send to the chat endpoint."
    )
    temperature: float = Field(
        default=0.2, description="Sampling temperature for the chat completion."
    )
    max_tokens: int | None = Field(
        default=None, description="Maximum tokens to generate in the completion."
    )
    top_p: float | None = Field(default=None, description="Nucleus sampling parameter.")
    stream: StrictBool = Field(
        default=False,
        description="Whether to request a streaming response.",
    )
    request_id: int | None = Field(
        default=None, description="Internal request identifier for tracing."
    )
    response_format: dict[str, Any] | None = Field(
        default=None, description="Structured output schema requested from the model."
    )
    model_override: str | None = Field(
        default=None, description="Override model name for this specific call."
    )
