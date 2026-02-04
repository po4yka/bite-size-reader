"""Chat request state tracking for the OpenRouter orchestrator.

Encapsulates the mutable state that persists across model fallbacks
and retry attempts within a single chat() call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatState:
    """Mutable state for a single chat() invocation.

    Tracks error context, response data, and structured output mode
    across model fallbacks and retry attempts.
    """

    # Structured output mode tracking
    builder_rf_mode_original: str
    response_format_initial: dict[str, Any] | None

    # Current mode (may be downgraded during retries)
    rf_mode_current: str | None = None
    response_format_current: dict[str, Any] | None = None

    # Response/error state accumulated across attempts
    last_error_text: str | None = None
    last_data: dict[str, Any] | None = None
    last_latency: int | None = None
    last_model_reported: str | None = None
    last_response_text: str | None = None
    last_error_context: dict[str, Any] | None = None

    # Structured output tracking
    structured_output_used: bool = False
    structured_output_mode_used: str | None = None
    structured_parse_error: bool = False

    # Message metrics (computed once, reused across attempts)
    message_lengths: list[int] = field(default_factory=list)
    message_roles: list[str] = field(default_factory=list)
    total_chars: int = 0

    def __post_init__(self) -> None:
        if self.rf_mode_current is None:
            self.rf_mode_current = self.builder_rf_mode_original
        if self.response_format_current is None:
            self.response_format_current = self.response_format_initial

    def update_from_result(self, result: dict[str, Any]) -> None:
        """Update state from an attempt result dict."""
        if "error_text" in result:
            self.last_error_text = result["error_text"]
        if "data" in result:
            self.last_data = result["data"]
        if "latency" in result:
            self.last_latency = result["latency"]
        if "model_reported" in result:
            self.last_model_reported = result["model_reported"]
        if "response_text" in result:
            self.last_response_text = result["response_text"]
        if "error_context" in result:
            self.last_error_context = result["error_context"]
        if "structured_parse_error" in result:
            self.structured_parse_error = result["structured_parse_error"]

    def update_retry_state(self, result: dict[str, Any]) -> None:
        """Update mode state when a retry is requested."""
        if "new_rf_mode" in result:
            self.rf_mode_current = result["new_rf_mode"]
        if "new_response_format" in result:
            self.response_format_current = result["new_response_format"]
        if "structured_output_used" in result:
            self.structured_output_used = result["structured_output_used"]
        if "structured_output_mode_used" in result:
            self.structured_output_mode_used = result["structured_output_mode_used"]
