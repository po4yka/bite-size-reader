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

    async def _persist_llm_call(self, llm: Any, req_id: int, correlation_id: str | None) -> None:
        if self._db_write_queue is not None:
            _llm = llm
            _req_id, _cid = req_id, correlation_id
            _model_fallback = self.cfg.openrouter.model

            async def _deferred_persist() -> None:
                try:
                    await self.llm_repo.async_insert_llm_call(
                        request_id=_req_id,
                        provider="openrouter",
                        model=_llm.model or _model_fallback,
                        endpoint=_llm.endpoint,
                        request_headers_json=_llm.request_headers or {},
                        request_messages_json=list(_llm.request_messages or []),
                        response_text=_llm.response_text,
                        response_json=_llm.response_json or {},
                        tokens_prompt=_llm.tokens_prompt,
                        tokens_completion=_llm.tokens_completion,
                        cost_usd=_llm.cost_usd,
                        latency_ms=_llm.latency_ms,
                        status=_llm.status,
                        error_text=_llm.error_text,
                        structured_output_used=getattr(_llm, "structured_output_used", None),
                        structured_output_mode=getattr(_llm, "structured_output_mode", None),
                        error_context_json=(
                            getattr(_llm, "error_context", {})
                            if getattr(_llm, "error_context", None) is not None
                            else None
                        ),
                    )
                except Exception as exc:
                    logger.exception(
                        "persist_llm_error",
                        extra={"error": str(exc), "cid": _cid},
                    )

            await self._db_write_queue.enqueue(
                _deferred_persist,
                operation_name="persist_llm_call",
                correlation_id=_cid or "",
            )
            return

        try:
            await self.llm_repo.async_insert_llm_call(
                request_id=req_id,
                provider="openrouter",
                model=llm.model or self.cfg.openrouter.model,
                endpoint=llm.endpoint,
                request_headers_json=llm.request_headers or {},
                request_messages_json=list(llm.request_messages or []),
                response_text=llm.response_text,
                response_json=llm.response_json or {},
                tokens_prompt=llm.tokens_prompt,
                tokens_completion=llm.tokens_completion,
                cost_usd=llm.cost_usd,
                latency_ms=llm.latency_ms,
                status=llm.status,
                error_text=llm.error_text,
                structured_output_used=getattr(llm, "structured_output_used", None),
                structured_output_mode=getattr(llm, "structured_output_mode", None),
                error_context_json=(
                    getattr(llm, "error_context", {})
                    if getattr(llm, "error_context", None) is not None
                    else None
                ),
            )
        except Exception as exc:
            logger.exception(
                "persist_llm_error",
                extra={"error": str(exc), "cid": correlation_id},
            )
