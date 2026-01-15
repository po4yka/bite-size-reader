"""Karakeep API client."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING, TypeVar

import httpx

from app.adapters.karakeep.models import (
    AttachTagRequest,
    CreateBookmarkRequest,
    KarakeepBookmark,
    KarakeepBookmarkList,
    KarakeepTag,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from typing import Self

logger = logging.getLogger(__name__)

T = TypeVar("T")

# HTTP status codes that should trigger a retry
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 30.0  # seconds
DEFAULT_JITTER = 0.1  # 10% jitter


class KarakeepClientError(Exception):
    """Base exception for Karakeep client errors."""


class KarakeepRetryableError(KarakeepClientError):
    """Error that can be retried."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _is_retryable_error(exc: Exception) -> bool:
    """Check if an exception is retryable.

    Args:
        exc: The exception to check

    Returns:
        True if the error should be retried
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
        return True
    return isinstance(exc, KarakeepRetryableError)


def _calculate_delay(attempt: int, base_delay: float, max_delay: float, jitter: float) -> float:
    """Calculate delay with exponential backoff and jitter.

    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        jitter: Jitter factor (0.1 = 10% random variation)

    Returns:
        Delay in seconds
    """
    delay = min(base_delay * (2**attempt), max_delay)
    jitter_amount = delay * jitter * random.random()
    return delay + jitter_amount


async def retry_with_backoff(
    func: Callable[[], Awaitable[T]],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: float = DEFAULT_JITTER,
    operation_name: str = "operation",
) -> T:
    """Execute an async function with exponential backoff retry.

    Args:
        func: Async function to execute
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries
        jitter: Random jitter factor to add to delay
        operation_name: Name of operation for logging

    Returns:
        Result of the function

    Raises:
        KarakeepClientError: If all retries are exhausted
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            last_exception = e

            if not _is_retryable_error(e):
                # Non-retryable error, raise immediately
                raise

            if attempt == max_retries:
                # Last attempt, raise the error
                logger.error(
                    "karakeep_retry_exhausted",
                    extra={
                        "operation": operation_name,
                        "attempts": attempt + 1,
                        "error": str(e),
                    },
                )
                raise KarakeepClientError(
                    f"{operation_name} failed after {attempt + 1} attempts: {e}"
                ) from e

            delay = _calculate_delay(attempt, base_delay, max_delay, jitter)
            logger.warning(
                "karakeep_retry_attempt",
                extra={
                    "operation": operation_name,
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "delay_seconds": round(delay, 2),
                    "error": str(e),
                },
            )
            await asyncio.sleep(delay)

    # Should not reach here, but type checker needs this
    raise KarakeepClientError(f"{operation_name} failed") from last_exception


class KarakeepClient:
    """Async HTTP client for Karakeep API."""

    # Default per-endpoint timeouts (seconds)
    DEFAULT_TIMEOUTS: dict[str, float] = {
        "get_bookmarks": 30.0,
        "get_all_bookmarks": 120.0,  # Longer for pagination
        "get_bookmark": 15.0,
        "create_bookmark": 30.0,
        "update_bookmark": 15.0,
        "delete_bookmark": 15.0,
        "attach_tags": 15.0,
        "detach_tag": 15.0,
        "get_tags": 30.0,
        "search_bookmarks": 30.0,
        "health_check": 10.0,
    }

    def __init__(
        self,
        api_url: str,
        api_key: str,
        timeout: float = 30.0,
        *,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay: float = DEFAULT_BASE_DELAY,
        retry_max_delay: float = DEFAULT_MAX_DELAY,
        endpoint_timeouts: dict[str, float] | None = None,
    ) -> None:
        """Initialize Karakeep client.

        Args:
            api_url: Base URL for Karakeep API (e.g., http://localhost:3000/api/v1/)
            api_key: API key for authentication
            timeout: Default request timeout in seconds
            max_retries: Maximum number of retry attempts for transient failures
            retry_base_delay: Base delay between retries in seconds
            retry_max_delay: Maximum delay between retries in seconds
            endpoint_timeouts: Custom per-endpoint timeouts (overrides defaults)
        """
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay
        # Merge custom endpoint timeouts with defaults
        self.endpoint_timeouts = {**self.DEFAULT_TIMEOUTS}
        if endpoint_timeouts:
            self.endpoint_timeouts.update(endpoint_timeouts)
        self._client: httpx.AsyncClient | None = None

    def get_timeout(self, endpoint: str) -> float:
        """Get timeout for a specific endpoint.

        Args:
            endpoint: Name of the endpoint (e.g., 'get_bookmarks')

        Returns:
            Timeout in seconds
        """
        return self.endpoint_timeouts.get(endpoint, self.timeout)

    async def __aenter__(self) -> Self:
        """Enter async context."""
        self._client = httpx.AsyncClient(
            base_url=self.api_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit async context."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client."""
        if self._client is None:
            raise KarakeepClientError("Client not initialized. Use async context manager.")
        return self._client

    async def _with_retry(
        self,
        func: Callable[[], Awaitable[T]],
        operation_name: str,
    ) -> T:
        """Execute a function with retry logic.

        Args:
            func: Async function to execute
            operation_name: Name of operation for logging

        Returns:
            Result of the function
        """
        return await retry_with_backoff(
            func,
            max_retries=self.max_retries,
            base_delay=self.retry_base_delay,
            max_delay=self.retry_max_delay,
            operation_name=operation_name,
        )

    async def get_bookmarks(
        self,
        limit: int = 100,
        cursor: str | None = None,
        archived: bool | None = None,
        favourited: bool | None = None,
    ) -> KarakeepBookmarkList:
        """Get paginated list of bookmarks.

        Args:
            limit: Maximum number of bookmarks to return
            cursor: Pagination cursor for next page
            archived: Filter by archived status
            favourited: Filter by favourited status

        Returns:
            Paginated list of bookmarks
        """
        params: dict[str, str | int | bool] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if archived is not None:
            params["archived"] = archived
        if favourited is not None:
            params["favourited"] = favourited

        timeout = self.get_timeout("get_bookmarks")

        async def _fetch() -> KarakeepBookmarkList:
            response = await self.client.get("/bookmarks", params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            return KarakeepBookmarkList.model_validate(data)

        return await self._with_retry(_fetch, "get_bookmarks")

    async def get_all_bookmarks(
        self,
        archived: bool | None = None,
        favourited: bool | None = None,
    ) -> list[KarakeepBookmark]:
        """Get all bookmarks (handles pagination).

        Args:
            archived: Filter by archived status
            favourited: Filter by favourited status

        Returns:
            List of all bookmarks
        """
        all_bookmarks: list[KarakeepBookmark] = []
        cursor: str | None = None

        while True:
            result = await self.get_bookmarks(
                limit=100,
                cursor=cursor,
                archived=archived,
                favourited=favourited,
            )
            all_bookmarks.extend(result.bookmarks)

            if not result.next_cursor:
                break
            cursor = result.next_cursor

        logger.info("karakeep_fetched_all_bookmarks", extra={"count": len(all_bookmarks)})
        return all_bookmarks

    async def get_bookmark(self, bookmark_id: str) -> KarakeepBookmark:
        """Get a single bookmark by ID.

        Args:
            bookmark_id: Bookmark ID

        Returns:
            Bookmark details
        """

        timeout = self.get_timeout("get_bookmark")

        async def _fetch() -> KarakeepBookmark:
            response = await self.client.get(f"/bookmarks/{bookmark_id}", timeout=timeout)
            response.raise_for_status()
            return KarakeepBookmark.model_validate(response.json())

        return await self._with_retry(_fetch, f"get_bookmark({bookmark_id})")

    async def create_bookmark(
        self,
        url: str,
        title: str | None = None,
        note: str | None = None,
    ) -> KarakeepBookmark:
        """Create a new bookmark.

        Args:
            url: URL to bookmark
            title: Optional title
            note: Optional note/description

        Returns:
            Created bookmark
        """
        request = CreateBookmarkRequest(
            type="link",
            url=url,
            title=title,
            note=note,
        )
        timeout = self.get_timeout("create_bookmark")

        async def _create() -> KarakeepBookmark:
            response = await self.client.post(
                "/bookmarks",
                json=request.model_dump(exclude_none=True),
                timeout=timeout,
            )
            response.raise_for_status()
            logger.info("karakeep_bookmark_created", extra={"url": url})
            return KarakeepBookmark.model_validate(response.json())

        return await self._with_retry(_create, "create_bookmark")

    async def update_bookmark(
        self,
        bookmark_id: str,
        title: str | None = None,
        note: str | None = None,
        archived: bool | None = None,
        favourited: bool | None = None,
    ) -> KarakeepBookmark:
        """Update a bookmark.

        Args:
            bookmark_id: Bookmark ID
            title: New title
            note: New note
            archived: Archive status
            favourited: Favourite status

        Returns:
            Updated bookmark
        """
        data: dict[str, str | bool] = {}
        if title is not None:
            data["title"] = title
        if note is not None:
            data["note"] = note
        if archived is not None:
            data["archived"] = archived
        if favourited is not None:
            data["favourited"] = favourited

        timeout = self.get_timeout("update_bookmark")

        async def _update() -> KarakeepBookmark:
            response = await self.client.patch(
                f"/bookmarks/{bookmark_id}", json=data, timeout=timeout
            )
            response.raise_for_status()
            return KarakeepBookmark.model_validate(response.json())

        return await self._with_retry(_update, f"update_bookmark({bookmark_id})")

    async def delete_bookmark(self, bookmark_id: str) -> None:
        """Delete a bookmark.

        Args:
            bookmark_id: Bookmark ID
        """
        timeout = self.get_timeout("delete_bookmark")

        async def _delete() -> None:
            response = await self.client.delete(f"/bookmarks/{bookmark_id}", timeout=timeout)
            response.raise_for_status()
            logger.info("karakeep_bookmark_deleted", extra={"bookmark_id": bookmark_id})

        await self._with_retry(_delete, f"delete_bookmark({bookmark_id})")

    async def attach_tags(self, bookmark_id: str, tags: list[str]) -> KarakeepBookmark:
        """Attach tags to a bookmark.

        Args:
            bookmark_id: Bookmark ID
            tags: List of tag names to attach

        Returns:
            Updated bookmark
        """
        request = AttachTagRequest(tags=[{"tagName": tag} for tag in tags])
        timeout = self.get_timeout("attach_tags")

        async def _attach() -> KarakeepBookmark:
            response = await self.client.post(
                f"/bookmarks/{bookmark_id}/tags",
                json=request.model_dump(),
                timeout=timeout,
            )
            response.raise_for_status()
            logger.debug("karakeep_tags_attached", extra={"bookmark_id": bookmark_id, "tags": tags})
            return KarakeepBookmark.model_validate(response.json())

        return await self._with_retry(_attach, f"attach_tags({bookmark_id})")

    async def detach_tag(self, bookmark_id: str, tag_id: str) -> None:
        """Detach a tag from a bookmark.

        Args:
            bookmark_id: Bookmark ID
            tag_id: Tag ID to detach
        """
        timeout = self.get_timeout("detach_tag")

        async def _detach() -> None:
            response = await self.client.delete(
                f"/bookmarks/{bookmark_id}/tags/{tag_id}", timeout=timeout
            )
            response.raise_for_status()

        await self._with_retry(_detach, f"detach_tag({bookmark_id}, {tag_id})")

    async def get_tags(self) -> list[KarakeepTag]:
        """Get all tags.

        Returns:
            List of all tags
        """
        timeout = self.get_timeout("get_tags")

        async def _fetch() -> list[KarakeepTag]:
            response = await self.client.get("/tags", timeout=timeout)
            response.raise_for_status()
            data = response.json()
            return [KarakeepTag.model_validate(tag) for tag in data.get("tags", [])]

        return await self._with_retry(_fetch, "get_tags")

    async def search_bookmarks(self, query: str, limit: int = 20) -> list[KarakeepBookmark]:
        """Search bookmarks.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching bookmarks
        """
        timeout = self.get_timeout("search_bookmarks")

        async def _search() -> list[KarakeepBookmark]:
            response = await self.client.get(
                "/bookmarks/search",
                params={"q": query, "limit": limit},
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            return [KarakeepBookmark.model_validate(b) for b in data.get("bookmarks", [])]

        return await self._with_retry(_search, "search_bookmarks")

    async def find_bookmark_by_url(self, url: str) -> KarakeepBookmark | None:
        """Find a bookmark by URL.

        Args:
            url: URL to search for

        Returns:
            Bookmark if found, None otherwise
        """
        # Search by URL - Karakeep might index URLs
        try:
            bookmarks = await self.search_bookmarks(url, limit=5)
            for bookmark in bookmarks:
                if bookmark.url == url:
                    return bookmark
        except KarakeepClientError as e:
            # Retries exhausted or non-retryable error
            logger.warning(
                "karakeep_find_by_url_failed",
                extra={"url": url, "error": str(e)},
            )
        except httpx.HTTPStatusError as e:
            # Non-retryable HTTP error (4xx)
            logger.warning(
                "karakeep_find_by_url_http_error",
                extra={"url": url, "status_code": e.response.status_code, "error": str(e)},
            )

        return None

    async def health_check(self) -> bool:
        """Check if Karakeep API is accessible.

        Returns:
            True if healthy
        """
        try:
            # Try to fetch first page of bookmarks as health check
            await self.get_bookmarks(limit=1)
            return True
        except Exception as e:
            logger.warning("karakeep_health_check_failed", extra={"error": str(e)})
            return False
