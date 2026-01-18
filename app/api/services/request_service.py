"""Request service - business logic for request operations."""

from datetime import datetime
from typing import Any

from app.api.exceptions import DuplicateResourceError, ResourceNotFoundError
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.core.url_utils import compute_dedupe_hash, normalize_url
from app.db.models import LLMCall, Request as RequestModel
from app.infrastructure.persistence.sqlite.repositories.crawl_result_repository import (
    SqliteCrawlResultRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)

logger = get_logger(__name__)


class RequestService:
    """Service for request-related business logic."""

    @staticmethod
    async def check_duplicate_url(user_id: int, url: str) -> dict | None:
        """
        Check if a URL has already been summarized by this user.

        Args:
            user_id: User ID for authorization
            url: URL to check

        Returns:
            Dictionary with duplicate info if found, None otherwise
        """
        from app.db.models import database_proxy

        request_repo = SqliteRequestRepositoryAdapter(database_proxy)
        summary_repo = SqliteSummaryRepositoryAdapter(database_proxy)

        normalized = normalize_url(url)
        dedupe_hash = compute_dedupe_hash(normalized)

        existing = await request_repo.async_get_request_by_dedupe_hash(dedupe_hash)

        if not existing or existing.get("user_id") != user_id:
            return None

        summary = await summary_repo.async_get_summary_by_request(existing["id"])

        return {
            "existing_request_id": existing["id"],
            "existing_summary_id": summary["id"] if summary else None,
            "summarized_at": existing["created_at"].isoformat() + "Z"
            if hasattr(existing["created_at"], "isoformat")
            else str(existing["created_at"]),
        }

    @staticmethod
    async def create_url_request(
        user_id: int, input_url: str, lang_preference: str = "auto"
    ) -> Any:
        """
        Create a new URL request.

        Args:
            user_id: User ID creating the request
            input_url: URL to process
            lang_preference: Language preference (auto, en, ru)

        Returns:
            Created Request object (dict or model)

        Raises:
            DuplicateResourceError: If URL already exists for this user
        """
        from app.db.models import database_proxy

        request_repo = SqliteRequestRepositoryAdapter(database_proxy)

        normalized = normalize_url(input_url)
        dedupe_hash = compute_dedupe_hash(normalized)

        # Check for duplicates
        duplicate_info = await RequestService.check_duplicate_url(user_id, input_url)
        if duplicate_info:
            raise DuplicateResourceError(
                "This URL was already summarized",
                existing_id=duplicate_info["existing_request_id"],
            )

        # Create request
        correlation_id = f"api-{user_id}-{int(datetime.now(UTC).timestamp())}"

        request_id = await request_repo.async_create_request(
            type_="url",
            status="pending",
            correlation_id=correlation_id,
            user_id=user_id,
            input_url=input_url,
            normalized_url=normalized,
            dedupe_hash=dedupe_hash,
            lang_detected=lang_preference,
        )

        new_request = await request_repo.async_get_request_by_id(request_id)

        logger.info(
            f"URL request created: {request_id}",
            extra={
                "request_id": request_id,
                "user_id": user_id,
                "correlation_id": correlation_id,
            },
        )

        # Return as object-like for backward compatibility if possible, or update caller
        from types import SimpleNamespace

        return SimpleNamespace(**new_request) if new_request else None

    @staticmethod
    async def create_forward_request(
        user_id: int,
        content_text: str,
        from_chat_id: int,
        from_message_id: int,
        lang_preference: str = "auto",
    ) -> Any:
        """
        Create a new forward message request.

        Args:
            user_id: User ID creating the request
            content_text: Forwarded message content
            from_chat_id: Source chat ID
            from_message_id: Source message ID
            lang_preference: Language preference

        Returns:
            Created Request object (dict or model)
        """
        from app.db.models import database_proxy

        request_repo = SqliteRequestRepositoryAdapter(database_proxy)

        correlation_id = f"api-{user_id}-{int(datetime.now(UTC).timestamp())}"

        request_id = await request_repo.async_create_request(
            type_="forward",
            status="pending",
            correlation_id=correlation_id,
            user_id=user_id,
            content_text=content_text,
            fwd_from_chat_id=from_chat_id,
            fwd_from_msg_id=from_message_id,
            lang_detected=lang_preference,
        )

        new_request = await request_repo.async_get_request_by_id(request_id)

        logger.info(
            f"Forward request created: {request_id}",
            extra={
                "request_id": request_id,
                "user_id": user_id,
                "correlation_id": correlation_id,
            },
        )

        from types import SimpleNamespace

        return SimpleNamespace(**new_request) if new_request else None

    @staticmethod
    async def get_request_by_id(user_id: int, request_id: int) -> dict:
        """
        Get request details with authorization check.

        Args:
            user_id: User ID for authorization
            request_id: Request ID to retrieve

        Returns:
            Dictionary with request details

        Raises:
            ResourceNotFoundError: If request not found or access denied
        """
        from app.db.models import database_proxy

        request_repo = SqliteRequestRepositoryAdapter(database_proxy)
        crawl_repo = SqliteCrawlResultRepositoryAdapter(database_proxy)
        summary_repo = SqliteSummaryRepositoryAdapter(database_proxy)

        request = await request_repo.async_get_request_by_id(request_id)

        if not request or request.get("user_id") != user_id:
            raise ResourceNotFoundError("Request", request_id)

        # Load related data
        crawl_result = await crawl_repo.async_get_crawl_result_by_request(request_id)
        # For llm_calls we don't have a direct repo method for list, we'll keep Peewee for now or add it
        llm_calls = list(LLMCall.select().where(LLMCall.request == request_id))
        summary = await summary_repo.async_get_summary_by_request(request_id)

        from types import SimpleNamespace

        return {
            "request": SimpleNamespace(**request),
            "crawl_result": SimpleNamespace(**crawl_result) if crawl_result else None,
            "llm_calls": llm_calls,
            "summary": SimpleNamespace(**summary) if summary else None,
        }

    @staticmethod
    async def get_request_status(user_id: int, request_id: int) -> dict:
        """
        Get processing status for a request.

        Args:
            user_id: User ID for authorization
            request_id: Request ID to check

        Returns:
            Dictionary with status information including:
            - stage: One of pending, crawling, processing, complete, failed
            - can_retry: Boolean indicating if request can be retried
            - queue_position: Position in queue (only for pending requests)

        Raises:
            ResourceNotFoundError: If request not found or access denied
        """
        from app.db.models import database_proxy

        request_repo = SqliteRequestRepositoryAdapter(database_proxy)
        crawl_repo = SqliteCrawlResultRepositoryAdapter(database_proxy)
        summary_repo = SqliteSummaryRepositoryAdapter(database_proxy)

        request = await request_repo.async_get_request_by_id(request_id)

        if not request or request.get("user_id") != user_id:
            raise ResourceNotFoundError("Request", request_id)

        status = request.get("status")
        # Determine stage based on status and related records
        # Stage values: pending, crawling, processing, complete, failed
        stage = "pending"  # Default
        progress = None
        queue_position = None
        error_stage = None
        error_type = None
        error_message = None
        can_retry = False  # Explicit boolean, never None

        if status == "processing":
            crawl_result = await crawl_repo.async_get_crawl_result_by_request(request_id)
            # Count llm calls via Peewee for now
            llm_calls_count = LLMCall.select().where(LLMCall.request == request_id).count()
            summary = await summary_repo.async_get_summary_by_request(request_id)

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
            # Calculate queue position
            queue_position = (
                RequestModel.select()
                .where(
                    (RequestModel.status == "pending")
                    & (RequestModel.created_at < request.get("created_at"))
                )
                .count()
            ) + 1  # 1-indexed position

        elif status in ("success", "ok"):
            stage = "complete"

        elif status == "error":
            stage = "failed"
            error_stage, error_type, error_message = await RequestService._derive_error_details(
                request_id
            )
            if not error_message:
                error_message = "Request failed"
            can_retry = True  # Failed requests can be retried

        elif status == "cancelled":
            stage = "failed"
            error_message = "Request was cancelled"
            can_retry = True  # Cancelled requests can be retried

        else:
            # Unknown status - treat as pending
            stage = "pending"

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
            "can_retry": can_retry,
            "correlation_id": request.get("correlation_id"),
        }

    @staticmethod
    async def retry_failed_request(user_id: int, request_id: int) -> Any:
        """
        Retry a failed request by creating a new one.

        Args:
            user_id: User ID for authorization
            request_id: Original request ID to retry

        Returns:
            Created Request object (dict or model)

        Raises:
            ResourceNotFoundError: If request not found or access denied
            ValueError: If request is not in error status
        """
        from app.db.models import database_proxy

        request_repo = SqliteRequestRepositoryAdapter(database_proxy)

        original_request = await request_repo.async_get_request_by_id(request_id)

        if not original_request or original_request.get("user_id") != user_id:
            raise ResourceNotFoundError("Request", request_id)

        if original_request.get("status") != "error":
            raise ValueError("Only failed requests can be retried")

        # Create new request with retry correlation ID
        correlation_id = f"{original_request.get('correlation_id')}-retry-1"

        new_request_id = await request_repo.async_create_request(
            type_=original_request.get("type"),
            status="pending",
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

        new_request = await request_repo.async_get_request_by_id(new_request_id)

        logger.info(
            f"Retry request created: {new_request_id} (original: {request_id})",
            extra={
                "new_request_id": new_request_id,
                "original_request_id": request_id,
                "user_id": user_id,
            },
        )

        from types import SimpleNamespace

        return SimpleNamespace(**new_request) if new_request else None

    @staticmethod
    async def _derive_error_details(
        request_id: int,
    ) -> tuple[str | None, str | None, str | None]:
        """
        Infer error stage/type/message from persisted artifacts.
        Prefers LLM errors (later stage) over crawl errors.
        """
        from app.db.models import database_proxy

        crawl_repo = SqliteCrawlResultRepositoryAdapter(database_proxy)

        # For llm_calls we don't have a direct repo method for latest, we'll use Peewee for now
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
                error_type = error_context.get("error_code")
                if message is None:
                    message = error_context.get("error_message")
            return (
                "llm_summarization",
                error_type or "LLM_FAILED",
                message or "LLM summarization failed",
            )

        latest_crawl = await crawl_repo.async_get_crawl_result_by_request(request_id)
        if latest_crawl and (
            latest_crawl.get("status") == "error" or latest_crawl.get("error_text")
        ):
            return (
                "content_extraction",
                latest_crawl.get("firecrawl_error_code") or "EXTRACTION_FAILED",
                latest_crawl.get("error_text")
                or latest_crawl.get("firecrawl_error_message")
                or "Content extraction failed",
            )

        return None, None, None
