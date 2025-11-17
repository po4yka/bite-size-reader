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


class UserInteractionRepository(Protocol):
    """Protocol for user interaction database operations."""

    async def async_insert_user_interaction(
        self,
        uid: int,
        cid: int,
        interaction_type: str,
        detail: str | None = None,
    ) -> int:
        """Insert a user interaction record.

        Returns:
            The ID of the inserted interaction.

        """
        ...

    async def async_update_user_interaction(
        self,
        interaction_id: int,
        completed: bool = False,
        error_message: str | None = None,
    ) -> None:
        """Update a user interaction record."""
        ...


class LLMCallRepository(Protocol):
    """Protocol for LLM call logging operations."""

    async def async_insert_llm_call(
        self,
        request_id: int,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        latency_ms: int,
        cost_usd: float | None = None,
        error: str | None = None,
    ) -> int:
        """Insert an LLM call log record.

        Returns:
            The ID of the inserted log record.

        """
        ...


class LLMClient(Protocol):
    """Protocol for LLM client implementations."""

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Any:
        """Send a chat request to the LLM.

        Args:
            messages: List of message dictionaries with 'role' and 'content'.
            model: Optional model name override.
            temperature: Optional temperature override.
            max_tokens: Optional max tokens override.
            **kwargs: Additional provider-specific parameters.

        Returns:
            LLM response object.

        """
        ...


class MessageFormatter(Protocol):
    """Protocol for formatting messages for display."""

    def format_summary(
        self,
        summary_data: dict[str, Any],
        include_insights: bool = False,
    ) -> str:
        """Format a summary for display.

        Args:
            summary_data: Dictionary containing summary information.
            include_insights: Whether to include insights section.

        Returns:
            Formatted message string.

        """
        ...

    def format_error(self, error_message: str, context: dict[str, Any] | None = None) -> str:
        """Format an error message for display.

        Args:
            error_message: The error message.
            context: Optional context information.

        Returns:
            Formatted error message string.

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

    async def check_and_update(self, user_id: int) -> tuple[bool, str | None]:
        """Check if user is rate limited and update counters.

        Args:
            user_id: The user identifier.

        Returns:
            Tuple of (is_allowed, error_message). error_message is None if allowed.

        """
        ...

    async def reset(self, user_id: int) -> None:
        """Reset rate limit counters for a user.

        Args:
            user_id: The user identifier.

        """
        ...
