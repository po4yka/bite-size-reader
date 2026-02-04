"""Protocol definitions for dependency inversion and interface segregation.

These protocols define contracts for major abstractions in the application,
allowing for loose coupling and easier testing.
"""

from typing import Any, Protocol


class RequestRepository(Protocol):
    """Protocol for request-related database operations."""

    async def async_create_request(
        self,
        uid: int,
        cid: int,
        url: str | None = None,
        lang: str | None = None,
        fwd_message_id: int | None = None,
        dedupe_hash: str | None = None,
        correlation_id: str | None = None,
    ) -> int:
        """Create a new request record.

        Returns:
            The ID of the created request.

        """
        ...

    async def async_get_request_by_id(self, request_id: int) -> dict[str, Any] | None:
        """Get a request by its ID.

        Returns:
            Dictionary with request data or None if not found.

        """
        ...

    async def async_get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict[str, Any] | None:
        """Get a request by its deduplication hash.

        Returns:
            Dictionary with request data or None if not found.

        """
        ...

    async def async_get_request_by_forward(
        self, cid: int, fwd_message_id: int
    ) -> dict[str, Any] | None:
        """Get a request by forwarded message details.

        Returns:
            Dictionary with request data or None if not found.

        """
        ...

    async def async_update_request_status(self, request_id: int, status: str) -> None:
        """Update the status of a request."""
        ...

    async def async_update_request_correlation_id(
        self, request_id: int, correlation_id: str
    ) -> None:
        """Update the correlation ID of a request."""
        ...

    async def async_update_request_lang_detected(self, request_id: int, lang: str) -> None:
        """Update the detected language of a request."""
        ...


class SummaryRepository(Protocol):
    """Protocol for summary-related database operations."""

    async def async_upsert_summary(
        self,
        request_id: int,
        lang: str,
        json_payload: dict[str, Any],
        insights_json: dict[str, Any] | None = None,
        is_read: bool = False,
    ) -> int:
        """Create or update a summary.

        Returns:
            The version number of the summary.

        """
        ...

    async def async_get_summary_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Get the latest summary for a request.

        Returns:
            Dictionary with summary data or None if not found.

        """
        ...

    async def async_get_unread_summaries(
        self,
        uid: int | None,
        cid: int | None,
        limit: int = 10,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get unread summaries for a user.

        Returns:
            List of dictionaries with summary data.

        """
        ...

    async def async_get_unread_summary_by_request_id(
        self, request_id: int
    ) -> dict[str, Any] | None:
        """Get an unread summary by request ID.

        Returns:
            Dictionary with summary data or None if not found or already read.

        """
        ...

    async def async_mark_summary_as_read(self, summary_id: int) -> None:
        """Mark a summary as read."""
        ...

    async def async_update_summary_insights(
        self, summary_id: int, insights_json: dict[str, Any]
    ) -> None:
        """Update the insights field of a summary."""
        ...


class CrawlResultRepository(Protocol):
    """Protocol for crawl result database operations."""

    async def async_insert_crawl_result(
        self,
        request_id: int,
        success: bool,
        markdown: str | None = None,
        error: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> int:
        """Insert a crawl result.

        Returns:
            The ID of the inserted crawl result.

        """
        ...

    async def async_get_crawl_result_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Get a crawl result by request ID.

        Returns:
            Dictionary with crawl result data or None if not found.

        """
        ...


class FileValidator(Protocol):
    """Protocol for file validation."""

    async def validate_file(
        self,
        file_path: str,
        max_size_mb: int | None = None,
        allowed_extensions: list[str] | None = None,
    ) -> tuple[bool, str | None]:
        """Validate a file for security and format.

        Args:
            file_path: Path to the file to validate.
            max_size_mb: Maximum allowed file size in megabytes.
            allowed_extensions: List of allowed file extensions.

        Returns:
            Tuple of (is_valid, error_message). error_message is None if valid.

        """
        ...


class RateLimiter(Protocol):
    """Protocol for rate limiting."""

    async def check_and_record(
        self, user_id: int, *, cost: int = 1, operation: str = "request"
    ) -> tuple[bool, str | None]:
        """Check if user is within rate limits and record the request.

        Args:
            user_id: The user identifier.
            cost: Cost weight for this operation (default: 1).
            operation: Description of operation for logging.

        Returns:
            Tuple of (is_allowed, error_message). error_message is None if allowed.

        """
        ...

    async def reset_user(self, user_id: int) -> None:
        """Reset rate limit counters for a user.

        Args:
            user_id: The user identifier.

        """
        ...
