"""Repository implementations that adapt the Database class to protocol interfaces.

These repositories provide focused interfaces for specific data access patterns,
implementing the Repository Pattern and adhering to Interface Segregation Principle.
"""

from typing import Any

from app.db.database import Database


class RequestRepositoryImpl:
    """Repository for request-related database operations.

    Adapts the Database class to provide a focused interface for request operations.
    """

    def __init__(self, database: Database) -> None:
        """Initialize the repository.

        Args:
            database: The database instance to wrap.
        """
        self._db = database

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
        """Create a new request record."""
        return await self._db.async_create_request(
            uid=uid,
            cid=cid,
            url=url,
            lang=lang,
            fwd_message_id=fwd_message_id,
            dedupe_hash=dedupe_hash,
            correlation_id=correlation_id,
        )

    async def async_get_request_by_id(self, request_id: int) -> dict[str, Any] | None:
        """Get a request by its ID."""
        return await self._db.async_get_request_by_id(request_id)

    async def async_get_request_by_dedupe_hash(
        self, dedupe_hash: str
    ) -> dict[str, Any] | None:
        """Get a request by its deduplication hash."""
        return await self._db.async_get_request_by_dedupe_hash(dedupe_hash)

    async def async_get_request_by_forward(
        self, cid: int, fwd_message_id: int
    ) -> dict[str, Any] | None:
        """Get a request by forwarded message details."""
        return await self._db.async_get_request_by_forward(cid, fwd_message_id)

    async def async_update_request_status(
        self, request_id: int, status: str
    ) -> None:
        """Update the status of a request."""
        await self._db.async_update_request_status(request_id, status)

    async def async_update_request_correlation_id(
        self, request_id: int, correlation_id: str
    ) -> None:
        """Update the correlation ID of a request."""
        await self._db.async_update_request_correlation_id(request_id, correlation_id)

    async def async_update_request_lang_detected(
        self, request_id: int, lang: str
    ) -> None:
        """Update the detected language of a request."""
        await self._db.async_update_request_lang_detected(request_id, lang)


class SummaryRepositoryImpl:
    """Repository for summary-related database operations.

    Adapts the Database class to provide a focused interface for summary operations.
    """

    def __init__(self, database: Database) -> None:
        """Initialize the repository.

        Args:
            database: The database instance to wrap.
        """
        self._db = database

    async def async_upsert_summary(
        self,
        request_id: int,
        lang: str,
        json_payload: dict[str, Any],
        insights_json: dict[str, Any] | None = None,
        is_read: bool = False,
    ) -> int:
        """Create or update a summary."""
        return await self._db.async_upsert_summary(
            request_id=request_id,
            lang=lang,
            json_payload=json_payload,
            insights_json=insights_json,
            is_read=is_read,
        )

    async def async_get_summary_by_request(
        self, request_id: int
    ) -> dict[str, Any] | None:
        """Get the latest summary for a request."""
        return await self._db.async_get_summary_by_request(request_id)

    async def async_get_unread_summaries(
        self, uid: int, cid: int, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get unread summaries for a user."""
        return await self._db.async_get_unread_summaries(uid, cid, limit)

    async def async_get_unread_summary_by_request_id(
        self, request_id: int
    ) -> dict[str, Any] | None:
        """Get an unread summary by request ID."""
        return await self._db.async_get_unread_summary_by_request_id(request_id)

    async def async_mark_summary_as_read(self, summary_id: int) -> None:
        """Mark a summary as read."""
        await self._db.async_mark_summary_as_read(summary_id)

    async def async_update_summary_insights(
        self, summary_id: int, insights_json: dict[str, Any]
    ) -> None:
        """Update the insights field of a summary."""
        await self._db.async_update_summary_insights(summary_id, insights_json)


class CrawlResultRepositoryImpl:
    """Repository for crawl result database operations.

    Adapts the Database class to provide a focused interface for crawl result operations.
    """

    def __init__(self, database: Database) -> None:
        """Initialize the repository.

        Args:
            database: The database instance to wrap.
        """
        self._db = database

    async def async_insert_crawl_result(
        self,
        request_id: int,
        success: bool,
        markdown: str | None = None,
        error: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> int:
        """Insert a crawl result."""
        return await self._db.async_insert_crawl_result(
            request_id=request_id,
            success=success,
            markdown=markdown,
            error=error,
            metadata_json=metadata_json,
        )

    async def async_get_crawl_result_by_request(
        self, request_id: int
    ) -> dict[str, Any] | None:
        """Get a crawl result by request ID."""
        return await self._db.async_get_crawl_result_by_request(request_id)


class UserInteractionRepositoryImpl:
    """Repository for user interaction database operations.

    Adapts the Database class to provide a focused interface for user interaction operations.
    """

    def __init__(self, database: Database) -> None:
        """Initialize the repository.

        Args:
            database: The database instance to wrap.
        """
        self._db = database

    async def async_insert_user_interaction(
        self,
        uid: int,
        cid: int,
        interaction_type: str,
        detail: str | None = None,
    ) -> int:
        """Insert a user interaction record."""
        return await self._db.async_insert_user_interaction(
            uid=uid,
            cid=cid,
            interaction_type=interaction_type,
            detail=detail,
        )

    async def async_update_user_interaction(
        self,
        interaction_id: int,
        completed: bool = False,
        error_message: str | None = None,
    ) -> None:
        """Update a user interaction record."""
        await self._db.async_update_user_interaction(
            interaction_id=interaction_id,
            completed=completed,
            error_message=error_message,
        )


class LLMCallRepositoryImpl:
    """Repository for LLM call logging operations.

    Adapts the Database class to provide a focused interface for LLM call logging.
    """

    def __init__(self, database: Database) -> None:
        """Initialize the repository.

        Args:
            database: The database instance to wrap.
        """
        self._db = database

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
        """Insert an LLM call log record."""
        return await self._db.async_insert_llm_call(
            request_id=request_id,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            error=error,
        )
