"""Request builder for OpenRouter API calls."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.adapters.openrouter.exceptions import ValidationError

if TYPE_CHECKING:
    from app.models.llm.llm_models import ChatRequest


class RequestBuilder:
    """Builds and validates HTTP requests for OpenRouter API."""

    def __init__(
        self,
        api_key: str,
        http_referer: str | None = None,
        x_title: str | None = None,
        provider_order: list[str] | tuple[str, ...] | None = None,
        enable_structured_outputs: bool = True,
        structured_output_mode: str = "json_schema",
        require_parameters: bool = True,
    ) -> None:
        self._api_key = api_key
        self._http_referer = http_referer
        self._x_title = x_title
        self._provider_order = list(provider_order or [])
        self._enable_structured_outputs = enable_structured_outputs
        self._structured_output_mode = structured_output_mode
        self._require_parameters = require_parameters

    def validate_chat_request(self, request: ChatRequest) -> None:
        """Validate chat request parameters."""
        # Security: Validate messages
        if not request.messages or not isinstance(request.messages, list):
            msg = "Messages list is required"
            raise ValidationError(
                msg,
                context={"messages_count": len(request.messages) if request.messages else 0},
            )
        if len(request.messages) > 50:  # Prevent extremely long conversations
            msg = f"Too many messages (max 50, got {len(request.messages)})"
            raise ValidationError(
                msg,
                context={"messages_count": len(request.messages)},
            )

        for i, message in enumerate(request.messages):
            if not isinstance(message, dict):
                error_msg = f"Message {i} must be a dictionary, got {type(message).__name__}"
                raise ValidationError(
                    error_msg,
                    context={"message_index": i, "message_type": type(message).__name__},
                )
            if "role" not in message or "content" not in message:
                error_msg = f"Message {i} missing required fields 'role' or 'content'"
                raise ValidationError(
                    error_msg,
                    context={
                        "message_index": i,
                        "missing_fields": [k for k in ["role", "content"] if k not in message],
                    },
                )
            if not isinstance(message["role"], str) or message["role"] not in {
                "system",
                "user",
                "assistant",
            }:
                error_msg = f"Message {i} has invalid role '{message.get('role', 'missing')}', must be one of: system, user, assistant"
                raise ValidationError(
                    error_msg,
                    context={
                        "message_index": i,
                        "invalid_role": message.get("role"),
                        "valid_roles": ["system", "user", "assistant"],
                    },
                )
            if not isinstance(message["content"], str):
                error_msg = (
                    f"Message {i} content must be string, got {type(message['content']).__name__}"
                )
                raise ValidationError(
                    error_msg,
                    context={"message_index": i, "content_type": type(message["content"]).__name__},
                )

        # Validate other parameters
        if not isinstance(request.temperature, int | float):
            msg = f"Temperature must be numeric, got {type(request.temperature).__name__}"
            raise ValidationError(
                msg,
                context={
                    "parameter": "temperature",
                    "value": request.temperature,
                    "type": type(request.temperature).__name__,
                },
            )
        if request.temperature < 0 or request.temperature > 2:
            msg = f"Temperature must be between 0 and 2, got {request.temperature}"
            raise ValidationError(
                msg,
                context={"parameter": "temperature", "value": request.temperature},
            )

        if request.max_tokens is not None:
            if not isinstance(request.max_tokens, int) or request.max_tokens <= 0:
                msg = f"Max tokens must be a positive integer, got {request.max_tokens}"
                raise ValidationError(
                    msg,
                    context={
                        "parameter": "max_tokens",
                        "value": request.max_tokens,
                        "type": type(request.max_tokens).__name__,
                    },
                )
            if request.max_tokens > 100000:
                msg = f"Max tokens too large (max 100000, got {request.max_tokens})"
                raise ValidationError(
                    msg,
                    context={"parameter": "max_tokens", "value": request.max_tokens},
                )

        if request.top_p is not None:
            if not isinstance(request.top_p, int | float):
                msg = f"Top_p must be numeric, got {type(request.top_p).__name__}"
                raise ValidationError(
                    msg,
                    context={
                        "parameter": "top_p",
                        "value": request.top_p,
                        "type": type(request.top_p).__name__,
                    },
                )
            if request.top_p < 0 or request.top_p > 1:
                msg = f"Top_p must be between 0 and 1, got {request.top_p}"
                raise ValidationError(
                    msg,
                    context={"parameter": "top_p", "value": request.top_p},
                )

        if not isinstance(request.stream, bool):
            msg = f"Stream must be boolean, got {type(request.stream).__name__}"
            raise ValidationError(
                msg,
                context={
                    "parameter": "stream",
                    "value": request.stream,
                    "type": type(request.stream).__name__,
                },
            )

        if request.request_id is not None and (
            not isinstance(request.request_id, int) or request.request_id <= 0
        ):
            msg = f"Invalid request_id (must be positive integer, got {request.request_id})"
            raise ValidationError(
                msg,
                context={
                    "parameter": "request_id",
                    "value": request.request_id,
                    "type": type(request.request_id).__name__,
                },
            )

    def sanitize_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Sanitize user content to prevent prompt injection."""
        patterns = [
            r"(?i)ignore previous instructions",
            r"(?i)forget previous instructions",
            r"(?i)system:",
            r"(?i)assistant:",
            r"(?i)user:",
            r"```",
        ]

        sanitized_messages = []
        for msg in messages:
            if msg["role"] == "user":
                sanitized_content = msg["content"]
                for pat in patterns:
                    sanitized_content = re.sub(
                        pat,
                        "",
                        sanitized_content,
                    )
                if sanitized_content != msg["content"]:
                    msg = {**msg, "content": sanitized_content}
            sanitized_messages.append(msg)
        return sanitized_messages

    def build_headers(self) -> dict[str, str]:
        """Build HTTP headers for the request."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": (self._http_referer or "https://github.com/your-repo"),
            "X-Title": self._x_title or "Bite-Size Reader Bot",
        }

    def build_request_body(
        self,
        model: str,
        messages: list[dict[str, str]],
        request: ChatRequest,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the request body for the API call."""
        body = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
        }

        # Add optional parameters
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.stream:
            body["stream"] = request.stream

        # GPT-5 specific optimizations for fewer restrictions
        model_lower = model.lower()
        if "gpt-5" in model_lower:
            # Enable thinking time for GPT-5 - use extended reasoning
            body["thinking"] = "extended"
            # Allow GPT-5 to use its full reasoning capabilities
            if "max_tokens" not in body or (
                isinstance(body["max_tokens"], int) and body["max_tokens"] < 16384
            ):
                body["max_tokens"] = 16384  # Ensure minimum for reasoning
            # Reduce temperature slightly for more focused reasoning
            if request.temperature > 0.5:
                body["temperature"] = 0.4
            # Enable top_p for better diversity in reasoning
            if request.top_p is None:
                body["top_p"] = 0.9

        # Provider routing configuration
        provider_prefs: dict[str, Any] = {}
        if self._provider_order:
            provider_prefs["order"] = list(self._provider_order)

        # Add response format if structured outputs enabled
        if response_format and self._enable_structured_outputs:
            built_rf = self._build_response_format(response_format, self._structured_output_mode)
            if built_rf:
                body["response_format"] = built_rf

        # Attach provider preferences
        if provider_prefs:
            body["provider"] = provider_prefs

        return body

    def _build_response_format(
        self, response_format: dict[str, Any] | None, mode: str
    ) -> dict[str, Any] | None:
        """Build response format based on mode and input.

        Rules:
        - If caller passes a fully wrapped object (has "type"), pass through.
        - If caller passes a raw JSON Schema, wrap into OpenRouter shape when
          mode == json_schema.
        - If mode == json_object, request a generic JSON object.
        """
        if not response_format or not self._enable_structured_outputs:
            return None

        # Pass-through for already-wrapped response_format
        rf_type = response_format.get("type") if isinstance(response_format, dict) else None
        if isinstance(rf_type, str) and rf_type in {
            "json_schema",
            "json_object",
        }:
            return response_format

        # Caller provided a raw schema or helper dict; wrap appropriately
        if mode == "json_schema":
            # Accept either {schema: {...}, name?, strict?} or a plain
            # JSON Schema
            json_schema_block = (
                response_format.get("schema") if isinstance(response_format, dict) else None
            )
            schema_obj = (
                json_schema_block if isinstance(json_schema_block, dict) else response_format
            )
            name_val = response_format.get("name") if isinstance(response_format, dict) else None
            strict_val = (
                response_format.get("strict") if isinstance(response_format, dict) else None
            )

            return {
                "type": "json_schema",
                "json_schema": {
                    "name": name_val or "schema",
                    "strict": (True if strict_val is None else bool(strict_val)),
                    "schema": (schema_obj if isinstance(schema_obj, dict) else {}),
                },
            }

        # Fallback to basic JSON object request
        return {"type": "json_object"}

    def should_apply_compression(
        self, messages: list[dict[str, str]], model: str
    ) -> tuple[bool, str | None]:
        """Determine if content compression should be applied."""
        total_content_length = sum(len(msg.get("content", "")) for msg in messages)
        model_lower = model.lower()

        if "gpt-5" in model_lower:
            compression_threshold = 800000
        elif "gpt-4o" in model_lower:
            compression_threshold = 350000
        elif "gemini-2.5" in model_lower:
            compression_threshold = 1200000
        else:
            compression_threshold = 200000

        if total_content_length > compression_threshold:
            return True, "middle-out"
        return False, None

    def get_redacted_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Get headers with sensitive information redacted."""
        redacted_headers = dict(headers)
        if "Authorization" in redacted_headers:
            redacted_headers["Authorization"] = "REDACTED"
        return redacted_headers
