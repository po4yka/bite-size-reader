"""Forward message summarization logic."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.adapters.content.llm_response_workflow import (
    LLMInteractionConfig,
    LLMRepairContext,
    LLMRequestConfig,
    LLMResponseWorkflow,
    LLMSummaryPersistenceSettings,
    LLMWorkflowNotifications,
)
from app.core.lang import LANG_RU

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.openrouter.openrouter_client import OpenRouterClient
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


class ForwardSummarizer:
    """Handles AI summarization for forwarded messages."""

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        openrouter: OpenRouterClient,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        sem: Callable[[], Any],
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.openrouter = openrouter
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._sem = sem
        self._workflow = LLMResponseWorkflow(
            cfg=cfg,
            db=db,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
        )

    async def summarize_forward(
        self,
        message: Any,
        prompt: str,
        chosen_lang: str,
        system_prompt: str,
        req_id: int,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Summarize forwarded message content."""
        # Truncate content if too long
        max_content_length = 45000  # Leave some buffer for the prompt
        if len(prompt) > max_content_length:
            prompt = prompt[:max_content_length] + "\n\n[Content truncated due to length]"
            logger.warning(
                "content_truncated",
                extra={
                    "original_length": len(prompt),
                    "truncated_length": max_content_length,
                    "cid": correlation_id,
                },
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Summarize the following message to the specified JSON schema. "
                    f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}.\n\n{prompt}"
                ),
            },
        ]

        forward_tokens = max(2048, min(6144, len(prompt) // 4 + 2048))

        response_format = self._workflow.build_structured_response_format()
        requests = [
            LLMRequestConfig(
                messages=messages,
                response_format=response_format,
                max_tokens=forward_tokens,
                temperature=self.cfg.openrouter.temperature,
                top_p=self.cfg.openrouter.top_p,
            )
        ]

        repair_context = LLMRepairContext(
            base_messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Summarize the following message to the specified JSON schema. "
                        f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}.\n\n{prompt}"
                    ),
                },
            ],
            repair_response_format=self._workflow.build_structured_response_format(),
            repair_max_tokens=forward_tokens,
            default_prompt=(
                "Your previous message was not a valid JSON object. Respond with ONLY a corrected JSON "
                "that matches the schema exactly."
            ),
        )

        async def _on_completion(llm_result: Any, _: LLMRequestConfig) -> None:
            await self.response_formatter.send_forward_completion_notification(message, llm_result)

        async def _on_llm_error(llm_result: Any, details: str | None) -> None:
            await self.response_formatter.send_error_notification(
                message,
                "llm_error",
                correlation_id or "unknown",
                details=details,
            )

        async def _on_processing_failure() -> None:
            await self.response_formatter.send_error_notification(
                message,
                "processing_failed",
                correlation_id or "unknown",
            )

        notifications = LLMWorkflowNotifications(
            completion=_on_completion,
            llm_error=_on_llm_error,
            repair_failure=_on_processing_failure,
            parsing_failure=_on_processing_failure,
        )

        interaction_config = LLMInteractionConfig(
            interaction_id=interaction_id,
            success_kwargs={
                "response_sent": True,
                "response_type": "summary",
                "request_id": req_id,
            },
            llm_error_builder=lambda llm_result, details: {
                "response_sent": True,
                "response_type": "error",
                "error_occurred": True,
                "error_message": details
                or f"LLM error: {llm_result.error_text or 'Unknown error'}",
                "request_id": req_id,
            },
            repair_failure_kwargs={
                "response_sent": True,
                "response_type": "error",
                "error_occurred": True,
                "error_message": "Invalid summary format",
                "request_id": req_id,
            },
            parsing_failure_kwargs={
                "response_sent": True,
                "response_type": "error",
                "error_occurred": True,
                "error_message": "Invalid summary format",
                "request_id": req_id,
            },
        )

        persistence = LLMSummaryPersistenceSettings(
            lang=chosen_lang,
            is_read=True,
        )

        return await self._workflow.execute_summary_workflow(
            message=message,
            req_id=req_id,
            correlation_id=correlation_id,
            interaction_config=interaction_config,
            persistence=persistence,
            repair_context=repair_context,
            requests=requests,
            notifications=notifications,
        )
