"""Application service for request submission, inspection, and retry flows."""

from __future__ import annotations

import inspect
import logging
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from peewee import OperationalError

from app.api.exceptions import DuplicateResourceError, ResourceNotFoundError
from app.core.time_utils import UTC
from app.core.url_utils import compute_dedupe_hash, normalize_url
from app.db.models import LLMCall, Request as RequestModel
from app.domain.models.request import RequestStatus

if TYPE_CHECKING:
    from app.application.ports import (
        CrawlResultRepositoryPort,
        LLMRepositoryPort,
        RequestRepositoryPort,
        SummaryRepositoryPort,
    )
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


class RequestService:
    """Service for request-related business logic."""

    def __init__(
        self,
        *,
        db: DatabaseSessionManager | None,
        request_repository: RequestRepositoryPort,
        summary_repository: SummaryRepositoryPort,
        crawl_result_repository: CrawlResultRepositoryPort,
        llm_repository: LLMRepositoryPort,
    ) -> None:
        self._db = db
        self._request_repo = request_repository
        self._summary_repo = summary_repository
        self._crawl_repo = crawl_result_repository
        self._llm_repo = llm_repository

    async def _request_context(self, request_id: int) -> dict[str, Any] | None:
        if inspect.iscoroutinefunction(
            getattr(type(self._request_repo), "async_get_request_context", None)
        ):
            try:
                return await self._request_repo.async_get_request_context(request_id)
            except OperationalError:
                return None
        return None

    async def _safe_get_summary_by_request(self, request_id: int) -> dict[str, Any] | None:
        try:
            return await self._summary_repo.async_get_summary_by_request(request_id)
        except OperationalError:
            return None

    async def check_duplicate_url(self, user_id: int, url: str) -> dict[str, Any] | None:
        normalized = normalize_url(url)
        dedupe_hash = compute_dedupe_hash(normalized)
        existing = await self._request_repo.async_get_request_by_dedupe_hash(dedupe_hash)
        if not existing or existing.get("user_id") != user_id:
            return None

        summary = await self._summary_repo.async_get_summary_by_request(existing["id"])
        return {
            "existing_request_id": existing["id"],
            "existing_summary_id": summary["id"] if summary else None,
            "summarized_at": existing["created_at"].isoformat() + "Z"
            if hasattr(existing["created_at"], "isoformat")
            else str(existing["created_at"]),
        }

    async def create_url_request(
        self,
        user_id: int,
        input_url: str,
        lang_preference: str = "auto",
    ) -> Any:
        normalized = normalize_url(input_url)
        dedupe_hash = compute_dedupe_hash(normalized)
        duplicate_info = await self.check_duplicate_url(user_id, input_url)
        if duplicate_info:
            raise DuplicateResourceError(
                "This URL was already summarized",
                existing_id=duplicate_info["existing_request_id"],
            )

        correlation_id = f"api-{user_id}-{int(datetime.now(UTC).timestamp())}"
        request_id = await self._request_repo.async_create_request(
            type_="url",
            status=RequestStatus.PENDING,
            correlation_id=correlation_id,
            user_id=user_id,
            input_url=input_url,
            normalized_url=normalized,
            dedupe_hash=dedupe_hash,
            lang_detected=lang_preference,
        )
        new_request = await self._request_repo.async_get_request_by_id(request_id)
        logger.info(
            "url_request_created",
            extra={"request_id": request_id, "user_id": user_id, "correlation_id": correlation_id},
        )
        return SimpleNamespace(**new_request) if new_request else None

    async def create_forward_request(
        self,
        user_id: int,
        content_text: str,
        from_chat_id: int,
        from_message_id: int,
        lang_preference: str = "auto",
    ) -> Any:
        correlation_id = f"api-{user_id}-{int(datetime.now(UTC).timestamp())}"
        request_id = await self._request_repo.async_create_request(
            type_="forward",
            status=RequestStatus.PENDING,
            correlation_id=correlation_id,
            user_id=user_id,
            content_text=content_text,
            fwd_from_chat_id=from_chat_id,
            fwd_from_msg_id=from_message_id,
            lang_detected=lang_preference,
        )
        new_request = await self._request_repo.async_get_request_by_id(request_id)
        logger.info(
            "forward_request_created",
            extra={"request_id": request_id, "user_id": user_id, "correlation_id": correlation_id},
        )
        return SimpleNamespace(**new_request) if new_request else None

    async def get_request_by_id(self, user_id: int, request_id: int) -> dict[str, Any]:
        context = await self._request_context(request_id)
        request = (
            context["request"]
            if context
            else await self._request_repo.async_get_request_by_id(request_id)
        )
        if not request or request.get("user_id") != user_id:
            raise ResourceNotFoundError("Request", request_id)

        if context:
            crawl_result = context.get("crawl_result")
            summary = context.get("summary")
        else:
            crawl_result = await self._crawl_repo.async_get_crawl_result_by_request(request_id)
            summary = await self._safe_get_summary_by_request(request_id)

        llm_calls = await self._llm_repo.async_get_llm_calls_by_request(request_id)
        return {
            "request": SimpleNamespace(**request),
            "crawl_result": SimpleNamespace(**crawl_result) if crawl_result else None,
            "llm_calls": [SimpleNamespace(**call) for call in llm_calls],
            "summary": SimpleNamespace(**summary) if summary else None,
        }

    async def get_request_status(self, user_id: int, request_id: int) -> dict[str, Any]:
        context = await self._request_context(request_id)
        request = (
            context["request"]
            if context
            else await self._request_repo.async_get_request_by_id(request_id)
        )
        if not request or request.get("user_id") != user_id:
            raise ResourceNotFoundError("Request", request_id)

        status = request.get("status")
        stage = "pending"
        progress = None
        queue_position = None
        error_stage = None
        error_type = None
        error_message = None
        error_reason_code = None
        retryable = False
        debug = None
        can_retry = False

        if status == "processing":
            if context:
                crawl_result = context.get("crawl_result")
                summary = context.get("summary")
            else:
                crawl_result = await self._crawl_repo.async_get_crawl_result_by_request(request_id)
                summary = await self._safe_get_summary_by_request(request_id)
            llm_calls_count = await self._llm_repo.async_count_llm_calls_by_request(request_id)
            if not crawl_result:
                stage = "crawling"
                progress = {"current_step": 1, "total_steps": 3, "percentage": 33}
            elif llm_calls_count == 0 or not summary:
                stage = "processing"
                progress = {"current_step": 2, "total_steps": 3, "percentage": 66}
            else:
                stage = "processing"
                progress = {"current_step": 3, "total_steps": 3, "percentage": 90}
        elif status == "pending":
            stage = "pending"
            queue_position = (
                RequestModel.select()
                .where(
                    (RequestModel.status == "pending")
                    & (RequestModel.created_at < request.get("created_at"))
                )
                .count()
            ) + 1
        elif status in ("success", "ok"):
            stage = "complete"
        elif status == "error":
            stage = "failed"
            (
                error_stage,
                error_type,
                error_message,
                error_reason_code,
                retryable,
                debug,
            ) = await self._derive_error_details(request_id)
            if not error_message:
                error_message = "Request failed"
            can_retry = True
        elif status == "cancelled":
            stage = "failed"
            error_message = "Request was cancelled"
            error_reason_code = "REQUEST_CANCELLED"
            retryable = True
            can_retry = True

        return {
            "request_id": request_id,
            "status": status,
            "stage": stage,
            "progress": progress,
            "estimated_seconds_remaining": 8 if stage in ("crawling", "processing") else None,
            "queue_position": queue_position,
            "error_stage": error_stage,
            "error_type": error_type,
            "error_message": error_message,
            "error_reason_code": error_reason_code,
            "retryable": retryable,
            "debug": debug,
            "can_retry": can_retry,
            "correlation_id": request.get("correlation_id"),
        }

    async def retry_failed_request(self, user_id: int, request_id: int) -> Any:
        original_request = await self._request_repo.async_get_request_by_id(request_id)
        if not original_request or original_request.get("user_id") != user_id:
            raise ResourceNotFoundError("Request", request_id)
        if original_request.get("status") != "error":
            raise ValueError("Only failed requests can be retried")

        correlation_id = f"{original_request.get('correlation_id')}-retry-1"
        new_request_id = await self._request_repo.async_create_request(
            type_=original_request.get("type"),
            status=RequestStatus.PENDING,
            correlation_id=correlation_id,
            user_id=user_id,
            input_url=original_request.get("input_url"),
            normalized_url=original_request.get("normalized_url"),
            dedupe_hash=original_request.get("dedupe_hash"),
            content_text=original_request.get("content_text"),
            fwd_from_chat_id=original_request.get("fwd_from_chat_id"),
            fwd_from_msg_id=original_request.get("fwd_from_msg_id"),
            lang_detected=original_request.get("lang_detected"),
        )
        new_request = await self._request_repo.async_get_request_by_id(new_request_id)
        logger.info(
            "retry_request_created",
            extra={
                "new_request_id": new_request_id,
                "original_request_id": request_id,
                "user_id": user_id,
            },
        )
        return SimpleNamespace(**new_request) if new_request else None

    async def _derive_error_details(
        self,
        request_id: int,
    ) -> tuple[str | None, str | None, str | None, str | None, bool, dict[str, Any] | None]:
        request_ctx = await self._request_repo.async_get_request_error_context(request_id)
        if request_ctx:
            reason_code = request_ctx.get("reason_code")
            error_type = request_ctx.get("error_type") or reason_code
            message = request_ctx.get("error_message") or "Request failed"
            stage = request_ctx.get("stage") or "unknown"
            retryable = bool(request_ctx.get("retryable", True))
            debug = {
                "pipeline": request_ctx.get("pipeline"),
                "component": request_ctx.get("component"),
                "attempt": request_ctx.get("attempt"),
                "max_attempts": request_ctx.get("max_attempts"),
                "timestamp": request_ctx.get("timestamp"),
            }
            return stage, error_type, message, reason_code, retryable, debug

        latest_llm = (
            LLMCall.select()
            .where(LLMCall.request == request_id)
            .order_by(LLMCall.updated_at.desc())
            .first()
        )
        if latest_llm and (latest_llm.status == "error" or latest_llm.error_text):
            error_context = latest_llm.error_context_json or {}
            error_type = None
            message = latest_llm.error_text
            if isinstance(error_context, dict):
                error_type = error_context.get("status_code")
                if message is None:
                    message = error_context.get("message")
            return (
                "llm_summarization",
                error_type or "LLM_FAILED",
                message or "LLM summarization failed",
                "LLM_FAILED",
                True,
                None,
            )

        latest_crawl = await self._crawl_repo.async_get_crawl_result_by_request(request_id)
        if latest_crawl and (
            latest_crawl.get("status") == "error" or latest_crawl.get("error_text")
        ):
            return (
                "content_extraction",
                latest_crawl.get("firecrawl_error_code") or "EXTRACTION_FAILED",
                latest_crawl.get("error_text")
                or latest_crawl.get("firecrawl_error_message")
                or "Content extraction failed",
                "EXTRACTION_FAILED",
                True,
                None,
            )

        return None, None, None, None, False, None
