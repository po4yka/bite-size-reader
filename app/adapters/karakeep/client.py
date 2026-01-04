"""Karakeep API client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from app.adapters.karakeep.models import (
    AttachTagRequest,
    CreateBookmarkRequest,
    KarakeepBookmark,
    KarakeepBookmarkList,
    KarakeepTag,
)

if TYPE_CHECKING:
    from typing import Self

logger = logging.getLogger(__name__)


class KarakeepClientError(Exception):
    """Base exception for Karakeep client errors."""


class KarakeepClient:
    """Async HTTP client for Karakeep API."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        """Initialize Karakeep client.

        Args:
            api_url: Base URL for Karakeep API (e.g., http://localhost:3000/api/v1/)
            api_key: API key for authentication
            timeout: Request timeout in seconds
        """
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

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

        response = await self.client.get("/bookmarks", params=params)
        response.raise_for_status()
        data = response.json()
        return KarakeepBookmarkList.model_validate(data)

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
        response = await self.client.get(f"/bookmarks/{bookmark_id}")
        response.raise_for_status()
        return KarakeepBookmark.model_validate(response.json())

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
        response = await self.client.post(
            "/bookmarks",
            json=request.model_dump(exclude_none=True),
        )
        response.raise_for_status()
        logger.info("karakeep_bookmark_created", extra={"url": url})
        return KarakeepBookmark.model_validate(response.json())

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

        response = await self.client.patch(f"/bookmarks/{bookmark_id}", json=data)
        response.raise_for_status()
        return KarakeepBookmark.model_validate(response.json())

    async def delete_bookmark(self, bookmark_id: str) -> None:
        """Delete a bookmark.

        Args:
            bookmark_id: Bookmark ID
        """
        response = await self.client.delete(f"/bookmarks/{bookmark_id}")
        response.raise_for_status()
        logger.info("karakeep_bookmark_deleted", extra={"bookmark_id": bookmark_id})

    async def attach_tags(self, bookmark_id: str, tags: list[str]) -> KarakeepBookmark:
        """Attach tags to a bookmark.

        Args:
            bookmark_id: Bookmark ID
            tags: List of tag names to attach

        Returns:
            Updated bookmark
        """
        request = AttachTagRequest(tags=[{"tagName": tag} for tag in tags])
        response = await self.client.post(
            f"/bookmarks/{bookmark_id}/tags",
            json=request.model_dump(),
        )
        response.raise_for_status()
        logger.debug("karakeep_tags_attached", extra={"bookmark_id": bookmark_id, "tags": tags})
        return KarakeepBookmark.model_validate(response.json())

    async def detach_tag(self, bookmark_id: str, tag_id: str) -> None:
        """Detach a tag from a bookmark.

        Args:
            bookmark_id: Bookmark ID
            tag_id: Tag ID to detach
        """
        response = await self.client.delete(f"/bookmarks/{bookmark_id}/tags/{tag_id}")
        response.raise_for_status()

    async def get_tags(self) -> list[KarakeepTag]:
        """Get all tags.

        Returns:
            List of all tags
        """
        response = await self.client.get("/tags")
        response.raise_for_status()
        data = response.json()
        return [KarakeepTag.model_validate(tag) for tag in data.get("tags", [])]

    async def search_bookmarks(self, query: str, limit: int = 20) -> list[KarakeepBookmark]:
        """Search bookmarks.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching bookmarks
        """
        response = await self.client.get(
            "/bookmarks/search",
            params={"q": query, "limit": limit},
        )
        response.raise_for_status()
        data = response.json()
        return [KarakeepBookmark.model_validate(b) for b in data.get("bookmarks", [])]

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
        except Exception:
            pass

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
