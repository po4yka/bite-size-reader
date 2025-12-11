"""Request service - business logic for request operations."""

from datetime import datetime

from app.api.exceptions import DuplicateResourceError, ResourceNotFoundError
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.core.url_utils import compute_dedupe_hash, normalize_url
from app.db.models import CrawlResult, LLMCall, Request as RequestModel, Summary

logger = get_logger(__name__)


class RequestService:
    """Service for request-related business logic."""

    @staticmethod
    def check_duplicate_url(user_id: int, url: str) -> dict | None:
        """
        Check if a URL has already been summarized by this user.

        Args:
            user_id: User ID for authorization
            url: URL to check

        Returns:
            Dictionary with duplicate info if found, None otherwise
        """
        normalized = normalize_url(url)
        dedupe_hash = compute_dedupe_hash(normalized)

        existing = (
            RequestModel.select()
            .where((RequestModel.dedupe_hash == dedupe_hash) & (RequestModel.user_id == user_id))
            .first()
        )

        if not existing:
            return None

        summary = Summary.select().where(Summary.request == existing.id).first()

        return {
            "existing_request_id": existing.id,
            "existing_summary_id": summary.id if summary else None,
            "summarized_at": existing.created_at.isoformat() + "Z",
        }

    @staticmethod
    def create_url_request(
        user_id: int, input_url: str, lang_preference: str = "auto"
    ) -> RequestModel:
        """
        Create a new URL request.

        Args:
            user_id: User ID creating the request
            input_url: URL to process
            lang_preference: Language preference (auto, en, ru)

        Returns:
            Created RequestModel instance

        Raises:
            DuplicateResourceError: If URL already exists for this user
        """
        normalized = normalize_url(input_url)
        dedupe_hash = compute_dedupe_hash(normalized)

        # Check for duplicates
        duplicate_info = RequestService.check_duplicate_url(user_id, input_url)
        if duplicate_info:
            raise DuplicateResourceError(
                "This URL was already summarized",
                existing_id=duplicate_info["existing_request_id"],
            )

        # Create request
        correlation_id = f"api-{user_id}-{int(datetime.now(UTC).timestamp())}"

        new_request = RequestModel.create(
            type="url",
            status="pending",
            correlation_id=correlation_id,
            user_id=user_id,
            input_url=input_url,
            normalized_url=normalized,
            dedupe_hash=dedupe_hash,
            lang_detected=lang_preference,
        )

        logger.info(
            f"URL request created: {new_request.id}",
            extra={
                "request_id": new_request.id,
                "user_id": user_id,
                "correlation_id": correlation_id,
            },
        )

        return new_request

    @staticmethod
    def create_forward_request(
        user_id: int,
        content_text: str,
        from_chat_id: int,
        from_message_id: int,
        lang_preference: str = "auto",
    ) -> RequestModel:
        """
        Create a new forward message request.

        Args:
            user_id: User ID creating the request
            content_text: Forwarded message content
            from_chat_id: Source chat ID
            from_message_id: Source message ID
            lang_preference: Language preference

        Returns:
            Created RequestModel instance
        """
        correlation_id = f"api-{user_id}-{int(datetime.now(UTC).timestamp())}"

        new_request = RequestModel.create(
            type="forward",
            status="pending",
            correlation_id=correlation_id,
            user_id=user_id,
            content_text=content_text,
            fwd_from_chat_id=from_chat_id,
            fwd_from_msg_id=from_message_id,
            lang_detected=lang_preference,
        )

        logger.info(
            f"Forward request created: {new_request.id}",
            extra={
                "request_id": new_request.id,
                "user_id": user_id,
                "correlation_id": correlation_id,
            },
        )

        return new_request

    @staticmethod
    def get_request_by_id(user_id: int, request_id: int) -> dict:
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
        request = (
            RequestModel.select()
            .where((RequestModel.id == request_id) & (RequestModel.user_id == user_id))
            .first()
        )

        if not request:
            raise ResourceNotFoundError("Request", request_id)

        # Load related data
        crawl_result = CrawlResult.select().where(CrawlResult.request == request.id).first()
        llm_calls = list(LLMCall.select().where(LLMCall.request == request.id))
        summary = Summary.select().where(Summary.request == request.id).first()

        return {
            "request": request,
            "crawl_result": crawl_result,
            "llm_calls": llm_calls,
            "summary": summary,
        }

    @staticmethod
    def get_request_status(user_id: int, request_id: int) -> dict:
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
        request = (
            RequestModel.select()
            .where((RequestModel.id == request_id) & (RequestModel.user_id == user_id))
            .first()
        )

        if not request:
            raise ResourceNotFoundError("Request", request_id)

        # Determine stage based on status and related records
        # Stage values: pending, crawling, processing, complete, failed
        stage = "pending"  # Default
        progress = None
        queue_position = None
        error_stage = None
        error_type = None
        error_message = None
        can_retry = False  # Explicit boolean, never None

        if request.status == "processing":
            crawl_result = CrawlResult.select().where(CrawlResult.request == request.id).first()
            llm_calls = LLMCall.select().where(LLMCall.request == request.id).count()
            summary = Summary.select().where(Summary.request == request.id).first()

            if not crawl_result:
                stage = "crawling"
                progress = {"current_step": 1, "total_steps": 3, "percentage": 33}
            elif llm_calls == 0 or not summary:
                stage = "processing"
                progress = {"current_step": 2, "total_steps": 3, "percentage": 66}
            else:
                stage = "processing"
                progress = {"current_step": 3, "total_steps": 3, "percentage": 90}

        elif request.status == "pending":
            stage = "pending"
            # Calculate queue position: count pending requests created before this one
            queue_position = (
                RequestModel.select()
                .where(
                    (RequestModel.status == "pending")
                    & (RequestModel.created_at < request.created_at)
                )
                .count()
            ) + 1  # 1-indexed position

        elif request.status in ("success", "ok"):
            stage = "complete"

        elif request.status == "error":
            stage = "failed"
            error_stage, error_type, error_message = RequestService._derive_error_details(
                request.id
            )
            if not error_message:
                error_message = "Request failed"
            can_retry = True  # Failed requests can be retried

        elif request.status == "cancelled":
            stage = "failed"
            error_message = "Request was cancelled"
            can_retry = True  # Cancelled requests can be retried

        else:
            # Unknown status - treat as pending
            stage = "pending"

        return {
            "request_id": request.id,
            "status": request.status,
            "stage": stage,
            "progress": progress,
            "estimated_seconds_remaining": 8 if stage in ("crawling", "processing") else None,
            "queue_position": queue_position,
            "error_stage": error_stage,
            "error_type": error_type,
            "error_message": error_message,
            "can_retry": can_retry,
            "correlation_id": request.correlation_id,
        }

    @staticmethod
    def retry_failed_request(user_id: int, request_id: int) -> RequestModel:
        """
        Retry a failed request by creating a new one.

        Args:
            user_id: User ID for authorization
            request_id: Original request ID to retry

        Returns:
            New RequestModel instance

        Raises:
            ResourceNotFoundError: If request not found or access denied
            ValueError: If request is not in error status
        """
        original_request = (
            RequestModel.select()
            .where((RequestModel.id == request_id) & (RequestModel.user_id == user_id))
            .first()
        )

        if not original_request:
            raise ResourceNotFoundError("Request", request_id)

        if original_request.status != "error":
            raise ValueError("Only failed requests can be retried")

        # Create new request with retry correlation ID
        correlation_id = f"{original_request.correlation_id}-retry-1"

        new_request = RequestModel.create(
            type=original_request.type,
            status="pending",
            correlation_id=correlation_id,
            user_id=user_id,
            input_url=original_request.input_url,
            normalized_url=original_request.normalized_url,
            dedupe_hash=original_request.dedupe_hash,
            content_text=original_request.content_text,
            fwd_from_chat_id=original_request.fwd_from_chat_id,
            fwd_from_msg_id=original_request.fwd_from_msg_id,
            lang_detected=original_request.lang_detected,
        )

        logger.info(
            f"Retry request created: {new_request.id} (original: {request_id})",
            extra={
                "new_request_id": new_request.id,
                "original_request_id": request_id,
                "user_id": user_id,
            },
        )

        return new_request

    @staticmethod
    def _derive_error_details(
        request_id: int,
    ) -> tuple[str | None, str | None, str | None]:
        """
        Infer error stage/type/message from persisted artifacts.
        Prefers LLM errors (later stage) over crawl errors.
        """
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

        latest_crawl = (
            CrawlResult.select()
            .where(CrawlResult.request == request_id)
            .order_by(CrawlResult.updated_at.desc())
            .first()
        )
        if latest_crawl and (latest_crawl.status == "error" or latest_crawl.error_text):
            return (
                "content_extraction",
                latest_crawl.firecrawl_error_code or "EXTRACTION_FAILED",
                latest_crawl.error_text
                or latest_crawl.firecrawl_error_message
                or "Content extraction failed",
            )

        return None, None, None
