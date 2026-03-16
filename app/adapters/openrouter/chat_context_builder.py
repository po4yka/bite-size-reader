from __future__ import annotations

import logging
from typing import Any

from app.adapters.openrouter.chat_models import (
    OpenRouterChatClient,
    PreparedChatContext,
    StructuredOutputState,
)
from app.adapters.openrouter.exceptions import ValidationError
from app.core.async_utils import raise_if_cancelled
from app.models.llm.llm_models import ChatRequest

logger = logging.getLogger(__name__)


class ChatContextBuilder:
    def __init__(self, client: OpenRouterChatClient) -> None:
        self._client = client

    def prepare(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float,
        max_tokens: int | None,
        top_p: float | None,
        stream: bool,
        request_id: int | None,
        response_format: dict[str, Any] | None,
        model_override: str | None,
        fallback_models_override: tuple[str, ...] | list[str] | None,
    ) -> PreparedChatContext:
        if not messages:
            msg = "Messages cannot be empty"
            raise ValidationError(msg, context={"messages_count": 0})
        if not isinstance(messages, list):
            msg = f"Messages must be a list, got {type(messages).__name__}"
            raise ValidationError(msg, context={"messages_type": type(messages).__name__})

        request = ChatRequest(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stream=stream,
            request_id=request_id,
            response_format=response_format,
            model_override=model_override,
        )
        try:
            self._client.request_builder.validate_chat_request(request)
            sanitized_messages = self._client.request_builder.sanitize_messages(messages)
        except Exception as exc:
            raise_if_cancelled(exc)
            msg = f"Request validation failed: {exc}"
            raise ValidationError(
                msg,
                context={"original_error": str(exc), "messages_count": len(messages)},
            ) from exc

        message_lengths = [len(str(message.get("content", ""))) for message in sanitized_messages]
        message_roles = [message.get("role", "?") for message in sanitized_messages]
        total_chars = sum(message_lengths)
        primary_model = model_override if model_override else self._client._model
        fallback_models = (
            list(fallback_models_override)
            if fallback_models_override
            else self._client._fallback_models
        )
        models_to_try = self._client.model_capabilities.build_model_fallback_list(
            primary_model,
            fallback_models,
            response_format,
            self._client._enable_structured_outputs,
        )
        if not models_to_try:
            msg = "No models available to try"
            raise ValueError(msg)

        return PreparedChatContext(
            request=request,
            sanitized_messages=sanitized_messages,
            message_lengths=message_lengths,
            message_roles=message_roles,
            total_chars=total_chars,
            primary_model=primary_model,
            models_to_try=models_to_try,
            response_format_initial=response_format if isinstance(response_format, dict) else None,
            initial_rf_mode=getattr(self._client.request_builder, "_structured_output_mode", None),
        )

    async def maybe_skip_unsupported_structured_model(
        self,
        *,
        model: str,
        primary_model: str,
        response_format: dict[str, Any] | None,
        request_id: int | None,
        structured_output_state: StructuredOutputState,
    ) -> tuple[bool, StructuredOutputState]:
        if not (response_format and self._client._enable_structured_outputs):
            return False, structured_output_state

        try:
            await self._client.model_capabilities.ensure_structured_supported_models()
            if self._client.model_capabilities.supports_structured_outputs(model):
                return False, structured_output_state
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.warning("Failed to check model capabilities: %s", exc)
            return False, structured_output_state

        reason = (
            "no_structured_outputs_primary" if model == primary_model else "no_structured_outputs"
        )
        self._client.error_handler.log_skip_model(model, reason, request_id)
        if model == primary_model:
            return False, StructuredOutputState()
        return True, structured_output_state
