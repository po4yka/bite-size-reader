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
from app.migration.worker_runtime import WorkerRunner, materialize_worker_llm_result
from app.utils.typing_indicator import typing_indicator

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.llm.protocol import LLMClientProtocol
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager
    from app.db.write_queue import DbWriteQueue

logger = logging.getLogger(__name__)

# Maximum character length for forward content sent to the LLM.
# Typical model context windows are ~128k tokens; 45k chars (~11k tokens) leaves
# ample room for the system prompt, response format schema, and generated output.
_MAX_FORWARD_CONTENT_CHARS = 45_000


class ForwardSummarizer:
    """Handles AI summarization for forwarded messages."""

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        openrouter: LLMClientProtocol,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        sem: Callable[[], Any],
        db_write_queue: DbWriteQueue | None = None,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.openrouter = openrouter
        self.response_formatter = response_formatter
        self._audit = audit_func
        self.sem = sem
        self.worker_runner = WorkerRunner(cfg.runtime)
        self._workflow = LLMResponseWorkflow(
            cfg=cfg,
            db=db,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
            db_write_queue=db_write_queue,
        )

    def _should_use_rust_worker(self, *, requests: list[LLMRequestConfig]) -> bool:
        if not self.worker_runner.enabled:
            return False
        if (
            str(getattr(self.cfg.runtime, "llm_provider", "openrouter")).strip().lower()
            != "openrouter"
        ):
            return False
        if self._summary_streaming_enabled():
            return False
        return all(not getattr(request, "stream", False) for request in requests)

    async def _persist_worker_attempts(
        self,
        *,
        worker_output: dict[str, Any],
        requests: list[LLMRequestConfig],
        req_id: int,
        correlation_id: str | None,
    ) -> list[tuple[Any, LLMRequestConfig]]:
        raw_attempts = worker_output.get("attempts")
        if not isinstance(raw_attempts, list):
            msg = "Rust worker returned invalid attempts payload"
            raise RuntimeError(msg)

        attempts: list[tuple[Any, LLMRequestConfig]] = []
        for index, item in enumerate(raw_attempts):
            if not isinstance(item, dict) or index >= len(requests):
                continue
            llm_payload = item.get("llm_result")
            if not isinstance(llm_payload, dict):
                continue
            llm_result = materialize_worker_llm_result(llm_payload)
            request = requests[index]
            await self._workflow.persist_llm_call(llm_result, req_id, correlation_id)
            attempts.append((llm_result, request))
        return attempts

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
        if len(prompt) > _MAX_FORWARD_CONTENT_CHARS:
            original_length = len(prompt)
            prompt = prompt[:_MAX_FORWARD_CONTENT_CHARS] + "\n\n[Content truncated due to length]"
            logger.warning(
                "content_truncated",
                extra={
                    "original_length": original_length,
                    "truncated_length": _MAX_FORWARD_CONTENT_CHARS,
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
        stream_coordinator = None
        if self._summary_streaming_enabled():
            from app.adapters.telegram.summary_draft_streaming import SummaryDraftStreamCoordinator

            stream_coordinator = SummaryDraftStreamCoordinator(
                response_formatter=self.response_formatter,
                message=message,
                correlation_id=correlation_id,
            )
            for request in requests:
                request.stream = True
                request.on_stream_delta = stream_coordinator.on_delta

        repair_context = LLMRepairContext(
            base_messages=messages,
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

        # Forwards are consumed immediately in Telegram (user sees the summary
        # inline), so they are pre-marked as read. URL summaries default to unread
        # because they may be reviewed later in the mobile app.
        persistence = LLMSummaryPersistenceSettings(
            lang=chosen_lang,
            is_read=True,
        )

        try:
            async with typing_indicator(self.response_formatter, message, action="typing"):
                if self._should_use_rust_worker(requests=requests):
                    worker_output = await self.worker_runner.execute_forward_text(
                        requests=requests,
                        correlation_id=correlation_id,
                        request_id=req_id,
                    )
                    attempts = await self._persist_worker_attempts(
                        worker_output=worker_output,
                        requests=requests,
                        req_id=req_id,
                        correlation_id=correlation_id,
                    )
                    terminal_index_raw = worker_output.get("terminal_attempt_index")
                    terminal_index = (
                        terminal_index_raw
                        if isinstance(terminal_index_raw, int)
                        and 0 <= terminal_index_raw < len(attempts)
                        else len(attempts) - 1
                    )
                    terminal_attempt = (
                        attempts[terminal_index] if attempts and terminal_index >= 0 else None
                    )
                    if terminal_attempt is not None and notifications.completion is not None:
                        await notifications.completion(terminal_attempt[0], terminal_attempt[1])

                    if worker_output.get("status") != "ok":
                        await self._workflow._handle_all_attempts_failed(
                            message,
                            req_id,
                            correlation_id,
                            interaction_config,
                            notifications,
                            attempts,
                        )
                        return None

                    summary = worker_output.get("summary")
                    if not isinstance(summary, dict):
                        msg = "Rust worker returned invalid summary payload"
                        raise RuntimeError(msg)
                    if terminal_attempt is None:
                        msg = "Rust worker completed without a terminal attempt"
                        raise RuntimeError(msg)
                    return await self._workflow._finalize_success(
                        summary,
                        terminal_attempt[0],
                        req_id,
                        correlation_id,
                        interaction_config,
                        persistence,
                        None,
                        None,
                        False,
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
        finally:
            if stream_coordinator is not None:
                await stream_coordinator.finalize()

    def _summary_streaming_enabled(self) -> bool:
        if not getattr(self.cfg.runtime, "summary_streaming_enabled", True):
            return False
        if getattr(self.cfg.runtime, "summary_streaming_mode", "section") != "section":
            return False
        telegram_cfg = getattr(self.cfg, "telegram", None)
        if telegram_cfg is None:
            return False
        if not getattr(telegram_cfg, "draft_streaming_enabled", True):
            return False

        scope = str(
            getattr(self.cfg.runtime, "summary_streaming_provider_scope", "openrouter")
        ).lower()
        if scope == "disabled":
            return False
        if scope == "all":
            return True
        provider_name = str(getattr(self.openrouter, "provider_name", "openrouter")).lower()
        return provider_name == scope
