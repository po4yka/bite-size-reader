"""Response processor for OpenRouter API responses."""

from __future__ import annotations

import json
from typing import Any

from app.core.json_utils import extract_json


class ResponseProcessor:
    """Processes and extracts content from OpenRouter API responses."""

    def __init__(self, enable_stats: bool = False) -> None:
        self._enable_stats = enable_stats

    def extract_structured_content(self, message_obj: dict, rf_included: bool) -> str | None:
        """Extract structured content from response message."""
        text = None

        # Prefer parsed field when structured outputs were requested
        if rf_included:
            parsed = message_obj.get("parsed")
            if parsed is not None:
                try:
                    text = json.dumps(parsed, ensure_ascii=False)
                except Exception:
                    text = str(parsed)

        # Fallback to content field
        if not text or (isinstance(text, str) and not text.strip()):
            content_field = message_obj.get("content")

            if isinstance(content_field, str):
                text = content_field
            elif isinstance(content_field, list):
                json_segments: list[str] = []
                text_segments: list[str] = []
                seen_json: set[str] = set()

                def append_json(value: Any) -> None:
                    json_str: str | None = None
                    if isinstance(value, dict | list):
                        try:
                            json_str = json.dumps(value, ensure_ascii=False)
                        except Exception:
                            return
                    elif isinstance(value, str):
                        stripped = value.strip()
                        if not stripped:
                            return
                        try:
                            parsed_value = json.loads(stripped)
                        except Exception:
                            return
                        if isinstance(parsed_value, dict | list):
                            json_str = json.dumps(parsed_value, ensure_ascii=False)
                        else:
                            return
                    else:
                        return

                    if json_str and json_str not in seen_json:
                        seen_json.add(json_str)
                        json_segments.append(json_str)

                def append_text(value: str) -> None:
                    stripped = value.strip()
                    if stripped:
                        text_segments.append(stripped)

                def maybe_append_text_or_json(value: str) -> None:
                    stripped = value.strip()
                    if not stripped:
                        return
                    try:
                        parsed_value = json.loads(stripped)
                    except Exception:
                        append_text(stripped)
                        return
                    if isinstance(parsed_value, dict | list):
                        append_json(parsed_value)
                    else:
                        append_text(stripped)

                def walk_content(part: Any) -> None:
                    if isinstance(part, dict):
                        for key in ("json", "parsed", "arguments", "output"):
                            if key in part:
                                append_json(part[key])

                        function_block = part.get("function")
                        if isinstance(function_block, dict):
                            append_json(function_block.get("arguments"))

                        tool_calls = part.get("tool_calls")
                        if isinstance(tool_calls, list):
                            for call in tool_calls:
                                walk_content(call)

                        for key in ("text", "content", "reasoning"):
                            value = part.get(key)
                            if isinstance(value, str):
                                maybe_append_text_or_json(value)
                            elif isinstance(value, list | dict):
                                walk_content(value)

                        for key in ("data", "payload", "message"):
                            nested = part.get(key)
                            if isinstance(nested, dict | list):
                                append_json(nested)

                    elif isinstance(part, list):
                        for item in part:
                            walk_content(item)
                    elif isinstance(part, str):
                        append_text(part)

                try:
                    walk_content(content_field)
                    if json_segments:
                        text = "\n".join(json_segments)
                    elif text_segments:
                        text = "\n".join(text_segments)
                except Exception:
                    pass

        # Try reasoning field for o1-style models
        if not text or (isinstance(text, str) and not text.strip()):
            reasoning = message_obj.get("reasoning")
            if reasoning and isinstance(reasoning, str):
                # Look for JSON in reasoning field
                start = reasoning.find("{")
                end = reasoning.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        potential_json = reasoning[start : end + 1]
                        json.loads(potential_json)  # Validate JSON
                        text = potential_json
                    except Exception:
                        text = reasoning

        # Try function/tool calls
        if not text or (isinstance(text, str) and not text.strip()):
            tool_calls = message_obj.get("tool_calls") or []
            if tool_calls and isinstance(tool_calls, list):
                try:
                    first = tool_calls[0] or {}
                    fn = (first.get("function") or {}) if isinstance(first, dict) else {}
                    args = fn.get("arguments")
                    if isinstance(args, str):
                        text = args
                    elif isinstance(args, dict):
                        text = json.dumps(args, ensure_ascii=False)
                except Exception:
                    pass

        return text

    def extract_response_data(
        self, data: dict, rf_included: bool
    ) -> tuple[str | None, dict, float | None]:
        """Extract response text, usage data, and cost from API response.

        If OPENROUTER usage.total_cost is present, use it. Otherwise, return None for cost
        and let the caller optionally compute it using model-specific pricing.
        """
        text = None
        usage = data.get("usage") or {}
        cost_usd = None

        # Extract response content
        try:
            choices = data.get("choices") or []
            if choices:
                message_obj = choices[0].get("message", {}) or {}
                text = self.extract_structured_content(message_obj, rf_included)
        except Exception:
            text = None

        # Calculate cost if enabled
        if self._enable_stats:
            try:
                raw = data.get("usage", {})
                if isinstance(raw, dict) and raw.get("total_cost") is not None:
                    cost_usd = float(raw.get("total_cost", 0.0))
                else:
                    cost_usd = None
            except Exception:
                cost_usd = None

        return text, usage, cost_usd

    def validate_structured_response(
        self, text: str | None, rf_included: bool, requested_rf: dict[str, Any] | None
    ) -> tuple[bool, str | None]:
        """Validate structured output response and return (is_valid, processed_text)."""
        if not rf_included or not requested_rf:
            return True, text

        text_str = text or ""
        parsed = extract_json(text_str)

        if parsed is not None:
            try:
                processed_text = json.dumps(parsed, ensure_ascii=False)
                return True, processed_text
            except Exception:
                return True, text_str
        else:
            # Invalid JSON with structured outputs
            return False, text_str

    def is_completion_truncated(self, data: dict) -> tuple[bool, str | None, str | None]:
        """Inspect response metadata and determine if the completion was truncated."""

        try:
            choices = data.get("choices") or []
            if not choices:
                return False, None, None

            first = choices[0] or {}
            finish_reason = first.get("finish_reason")
            native_finish_reason = first.get("native_finish_reason")

            finish_reason_str = finish_reason if isinstance(finish_reason, str) else None
            native_reason_str = (
                native_finish_reason if isinstance(native_finish_reason, str) else None
            )

            truncated = False
            if finish_reason_str:
                truncated = finish_reason_str.lower() in {"length", "max_tokens"}

            if native_reason_str and not truncated:
                normalized_native = native_reason_str.replace("-", "_").lower()
                if any(term in normalized_native for term in ("max_token", "length")):
                    truncated = True

            return truncated, finish_reason_str, native_reason_str
        except Exception:
            return False, None, None

    def should_downgrade_response_format(
        self, status_code: int, data: dict, rf_included: bool
    ) -> bool:
        """Check if response format should be downgraded due to errors."""
        if status_code == 400 and rf_included:
            err_dump = json.dumps(data).lower()
            return "response_format" in err_dump
        return False

    def get_error_context(self, status_code: int, data: dict) -> dict[str, Any]:
        """Return structured error context for logging and user messaging."""
        error_messages = {
            400: "Invalid or missing request parameters",
            401: "Authentication failed (invalid or expired API key)",
            402: "Insufficient account balance",
            403: "Access forbidden (API key limit exceeded or invalid permissions)",
            404: "Requested resource not found",
            429: "Rate limit exceeded",
            500: "Internal server error",
        }

        base_message = error_messages.get(status_code, f"HTTP {status_code} error")
        api_error = None
        if isinstance(data, dict):
            raw_error = data.get("error")
            if isinstance(raw_error, dict):
                api_error = raw_error.get("message") or raw_error.get("code")
            elif isinstance(raw_error, str):
                api_error = raw_error

        # Enhance error message for specific OpenRouter API errors
        if status_code == 403 and api_error:
            api_error_lower = str(api_error).lower()
            if "key limit exceeded" in api_error_lower:
                base_message = "API key usage limit exceeded. Please check your OpenRouter account limits or upgrade your plan."
            elif (
                "manage it using" in api_error_lower
                and "openrouter.ai/settings/keys" in api_error_lower
            ):
                base_message = "API key limit exceeded. Please manage your key limits at https://openrouter.ai/settings/keys"

        provider = None
        if isinstance(data, dict):
            provider = data.get("provider")
        provider_detail = None
        if isinstance(provider, dict):
            provider_detail = provider.get("name") or provider.get("id")
        elif isinstance(provider, str):
            provider_detail = provider

        context = {
            "status_code": status_code,
            "message": base_message,
            "api_error": api_error,
        }
        if provider_detail:
            context["provider"] = provider_detail
        return context
