"""Payload logging for OpenRouter API requests and responses."""

from __future__ import annotations

import logging

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
        self, headers: dict, body: dict, messages: list[dict], rf_mode: str | None
    ) -> None:
        """Log request payload for debugging."""
        if not self._debug_payloads:
            return

        redacted_headers = dict(headers)
        if "Authorization" in redacted_headers:
            redacted_headers["Authorization"] = "REDACTED"

        preview_rf = body.get("response_format") or {}
        rf_type = preview_rf.get("type") if isinstance(preview_rf, dict) else None

        # Calculate content lengths
        content_lengths = [len(msg.get("content", "")) for msg in messages]
        total_content = sum(content_lengths)

        # Show truncated messages for debug
        debug_messages = []
        for i, msg in enumerate(messages[:3]):
            debug_msg = dict(msg)
            content = debug_msg.get("content", "")
            if len(content) > 200:
                debug_msg["content"] = content[:100] + f"... [+{len(content) - 100} chars]"
            debug_msg["content_length"] = str(len(content))
            debug_messages.append(debug_msg)

        self._logger.debug(
            "openrouter_request_payload",
            extra={
                "headers": redacted_headers,
                "body_preview": {
                    "model": body.get("model"),
                    "messages": debug_messages,
                    "temperature": body.get("temperature"),
                    "response_format_type": rf_type,
                    "response_format_mode": rf_mode,
                    "total_content_length": total_content,
                    "content_lengths": content_lengths,
                    "transforms": body.get("transforms"),
                },
            },
        )

    def log_response_payload(self, data: dict) -> None:
        """Log response payload for debugging."""
        if not self._debug_payloads:
            return

        try:
            preview = data
            # Truncate large response content
            if isinstance(preview, dict) and "choices" in preview:
                choices = preview.get("choices", [])
                if choices and isinstance(choices[0], dict):
                    choice = choices[0]
                    if "message" in choice and isinstance(choice["message"], dict):
                        msg_content = choice["message"].get("content")
                        if msg_content and isinstance(msg_content, str):
                            truncated_content = truncate_log_content(
                                msg_content, self._log_truncate_length
                            )
                            choice["message"]["content"] = truncated_content

            self._logger.debug("openrouter_response_payload", extra={"preview": preview})
        except Exception:
            pass

    def log_request(
        self,
        model: str,
        attempt: int,
        messages_len: int,
        structured_output: bool,
        rf_mode: str | None,
    ) -> None:
        """Log basic request information."""
        self._logger.debug(
            "openrouter_request",
            extra={
                "model": model,
                "attempt": attempt,
                "messages_len": messages_len,
                "structured_output": structured_output,
                "rf_mode": rf_mode,
            },
        )

    def log_response(
        self,
        status: int,
        latency_ms: int,
        model: str,
    ) -> None:
        """Log basic response information."""
        self._logger.debug(
            "openrouter_response",
            extra={
                "status": status,
                "latency_ms": latency_ms,
                "model": model,
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
