"""Payload logging for OpenRouter API requests and responses."""

from __future__ import annotations

import logging
from typing import Any

from app.core.logging_utils import truncate_log_content


class PayloadLogger:
    """Handles request and response payload logging for debugging."""

    def __init__(
        self,
        debug_payloads: bool = False,
        log_truncate_length: int = 1000,
    ) -> None:
        self._debug_payloads = debug_payloads
        self._log_truncate_length = log_truncate_length
        self._logger = logging.getLogger(__name__)

    def log_request_payload(
        self,
        headers: dict[str, Any],
        body: dict[str, Any],
        messages: list[dict[str, Any]],
        rf_mode: str | None,
    ) -> None:
        """Log compact request preview when payload debugging is enabled."""
        if not self._debug_payloads:
            return

        redacted_headers = dict(headers)
        if "Authorization" in redacted_headers:
            redacted_headers["Authorization"] = "REDACTED"

        preview_rf = body.get("response_format") or {}
        rf_type = preview_rf.get("type") if isinstance(preview_rf, dict) else None

        content_lengths = [len(str(msg.get("content", ""))) for msg in messages]
        total_content = sum(content_lengths)

        message_summaries: list[dict[str, Any]] = []
        for msg in messages[:2]:
            role = msg.get("role", "?")
            content = str(msg.get("content", ""))
            message_summaries.append(
                {
                    "role": role,
                    "len": len(content),
                    "preview": truncate_log_content(content, 120),
                }
            )

        self._logger.debug(
            "openrouter_request_payload",
            extra={
                "headers": redacted_headers,
                "body_preview": {
                    "model": body.get("model"),
                    "temperature": body.get("temperature"),
                    "response_format_type": rf_type,
                    "response_format_mode": rf_mode,
                    "total_content_length": total_content,
                    "messages_total": len(messages),
                    "sample_messages": message_summaries,
                    "transforms": body.get("transforms"),
                },
            },
        )

    def log_response_payload(self, data: dict[str, Any]) -> None:
        """Log a compact response preview when payload debugging is enabled."""
        if not self._debug_payloads:
            return

        try:
            choice_preview: dict[str, Any] | None = None
            choices = data.get("choices") if isinstance(data, dict) else None
            if isinstance(choices, list) and choices:
                first = choices[0] or {}
                message = first.get("message") if isinstance(first, dict) else None
                content_preview = None
                reasoning_preview = None
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        content_preview = truncate_log_content(content, 200)
                    reasoning = message.get("reasoning")
                    if isinstance(reasoning, str):
                        reasoning_preview = truncate_log_content(reasoning, 200)
                choice_preview = {
                    "finish_reason": first.get("finish_reason"),
                    "native_finish_reason": first.get("native_finish_reason"),
                    "content_preview": content_preview,
                    "reasoning_preview": reasoning_preview,
                }

            preview = {
                "id": data.get("id") if isinstance(data, dict) else None,
                "model": data.get("model") if isinstance(data, dict) else None,
                "usage": data.get("usage") if isinstance(data, dict) else None,
                "choice": choice_preview,
            }

            self._logger.debug("openrouter_response_payload", extra={"preview": preview})
        except Exception:
            pass

    def log_request(
        self,
        *,
        model: str,
        attempt: int,
        request_id: int | None,
        message_lengths: list[int],
        message_roles: list[str],
        total_chars: int,
        structured_output: bool,
        rf_mode: str | None,
        transforms: list[str] | None,
    ) -> None:
        """Log concise request metadata for observability."""
        samples = [
            {"role": role, "len": length}
            for role, length in zip(message_roles[:3], message_lengths[:3], strict=False)
        ]
        extra = {
            "model": model,
            "attempt": attempt,
            "request_id": request_id,
            "messages": len(message_lengths),
            "sample_messages": samples,
            "total_chars": total_chars,
            "structured_output": structured_output,
            "rf_mode": rf_mode,
        }
        if transforms:
            extra["transforms"] = transforms

        self._logger.debug("openrouter_request", extra=extra)

    def log_response(
        self,
        *,
        status: int,
        latency_ms: int,
        model: str,
        attempt: int,
        request_id: int | None,
        truncated: bool,
        finish_reason: str | None,
        native_finish_reason: str | None,
        tokens_prompt: int | None,
        tokens_completion: int | None,
        tokens_total: int | None,
        cost_usd: float | None,
        structured_output: bool,
        rf_mode: str | None,
    ) -> None:
        """Log concise response metadata for observability."""
        self._logger.debug(
            "openrouter_response",
            extra={
                "status": status,
                "latency_ms": latency_ms,
                "model": model,
                "attempt": attempt,
                "request_id": request_id,
                "structured_output": structured_output,
                "rf_mode": rf_mode,
                "finish_reason": finish_reason,
                "native_finish_reason": native_finish_reason,
                "truncated": truncated,
                "tokens_prompt": tokens_prompt,
                "tokens_completion": tokens_completion,
                "tokens_total": tokens_total,
                "cost_usd": cost_usd,
            },
        )

    def log_compression_applied(
        self,
        total_content_length: int,
        threshold: int,
        model: str,
    ) -> None:
        """Log when content compression is applied."""
        self._logger.warning(
            "middle_out_compression_applied",
            extra={
                "total_content_length": total_content_length,
                "threshold": threshold,
                "model": model,
            },
        )
