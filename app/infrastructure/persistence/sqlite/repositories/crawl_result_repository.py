"""SQLite implementation of crawl result repository.

This adapter translates between crawl result data and database records.
"""

from typing import Any


class SqliteCrawlResultRepositoryAdapter:
    """Adapter that wraps the existing Database class for crawl result operations.

    This adapter implements the CrawlResultRepository protocol using the existing
    Database class, providing a bridge between the new domain layer and the
    existing infrastructure.
    """

    def __init__(self, database: Any) -> None:
        """Initialize the repository adapter.

        Args:
            database: The existing Database instance to wrap.

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
