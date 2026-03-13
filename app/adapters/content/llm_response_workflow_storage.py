"""Storage persistence mixin for LLM response workflow."""
# mypy: disable-error-code=attr-defined

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.adapters.content.llm_response_workflow")


class LLMWorkflowStorageMixin:
    """Persistence helpers for raw LLM calls."""

    # Explicit host contract for composition with LLMResponseWorkflow.
    _db_write_queue: Any
    cfg: Any
    llm_repo: Any

    def _build_llm_call_payload(self, llm: Any, req_id: int) -> dict[str, Any]:
        """Serialize an LLM call once so queue batching can reuse the payload."""
        return {
            "request_id": req_id,
            "provider": "openrouter",
            "model": llm.model or self.cfg.openrouter.model,
            "endpoint": llm.endpoint,
            "request_headers_json": llm.request_headers or {},
            "request_messages_json": list(llm.request_messages or []),
            "response_text": llm.response_text,
            "response_json": llm.response_json or {},
            "tokens_prompt": llm.tokens_prompt,
            "tokens_completion": llm.tokens_completion,
            "cost_usd": llm.cost_usd,
            "latency_ms": llm.latency_ms,
            "status": llm.status,
            "error_text": llm.error_text,
            "structured_output_used": getattr(llm, "structured_output_used", None),
            "structured_output_mode": getattr(llm, "structured_output_mode", None),
            "error_context_json": (
                getattr(llm, "error_context", {})
                if getattr(llm, "error_context", None) is not None
                else None
            ),
        }

    async def _persist_llm_calls_batch(self, calls: list[dict[str, Any]]) -> None:
        """Persist multiple LLM calls together when the queue can coalesce them."""
        try:
            await self.llm_repo.async_insert_llm_calls_batch(calls)
        except Exception as exc:
            logger.exception(
                "persist_llm_batch_error",
                extra={"error": str(exc), "count": len(calls)},
            )

    async def _persist_llm_call(self, llm: Any, req_id: int, correlation_id: str | None) -> None:
        payload = self._build_llm_call_payload(llm, req_id)

        if self._db_write_queue is not None:
            await self._db_write_queue.enqueue_batch(
                payload,
                batch_key=f"persist_llm_call:{id(self.llm_repo)}",
                execute_batch=self._persist_llm_calls_batch,
                operation_name="persist_llm_call",
                correlation_id=correlation_id or "",
            )
            return

        try:
            await self.llm_repo.async_insert_llm_call(**payload)
        except Exception as exc:
            logger.exception(
                "persist_llm_error",
                extra={"error": str(exc), "cid": correlation_id},
            )
