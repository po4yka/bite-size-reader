"""Bookmark caching and pagination helpers for Karakeep sync."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from app.adapters.karakeep.sync.constants import BOOKMARK_PAGE_SIZE
from app.core.url_utils import normalize_url

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.adapters.karakeep.models import KarakeepBookmark
    from app.adapters.karakeep.sync.protocols import KarakeepClientProtocol

logger = logging.getLogger(__name__)


class KarakeepBookmarkCache:
    def __init__(self) -> None:
        self._karakeep_url_index_cache: dict[str, KarakeepBookmark] | None = None
        self._karakeep_bookmarks_cache: list[KarakeepBookmark] | None = None
        self._allow_cache_reuse = False

    def reuse_enabled(self) -> bool:
        return self._allow_cache_reuse

    def clear(self) -> None:
        self._karakeep_url_index_cache = None
        self._karakeep_bookmarks_cache = None

    def clear_if_not_reusing(self) -> None:
        if not self._allow_cache_reuse:
            self.clear()

    def cached_bookmarks(self) -> list[KarakeepBookmark] | None:
        if not self._allow_cache_reuse:
            return None
        return self._karakeep_bookmarks_cache

    @asynccontextmanager
    async def scope(self) -> AsyncIterator[None]:
        previous = self._allow_cache_reuse
        self._allow_cache_reuse = True
        self.clear()
        try:
            yield
        finally:
            self._allow_cache_reuse = previous

    async def get_url_index(
        self,
        client: KarakeepClientProtocol,
        *,
        correlation_id: str,
    ) -> dict[str, KarakeepBookmark]:
        if self._allow_cache_reuse and self._karakeep_url_index_cache is not None:
            logger.debug(
                "karakeep_url_index_cache_hit",
                extra={
                    "correlation_id": correlation_id,
                    "count": len(self._karakeep_url_index_cache),
                },
            )
            return self._karakeep_url_index_cache

        index = await self._build_url_index(client, correlation_id=correlation_id)
        if self._allow_cache_reuse:
            self._karakeep_url_index_cache = index
        return index

    async def get_bookmarks(
        self,
        client: KarakeepClientProtocol,
        *,
        correlation_id: str,
    ) -> list[KarakeepBookmark]:
        if self._allow_cache_reuse and self._karakeep_bookmarks_cache is not None:
            logger.debug(
                "karakeep_bookmarks_cache_hit",
                extra={
                    "correlation_id": correlation_id,
                    "count": len(self._karakeep_bookmarks_cache),
                },
            )
            return self._karakeep_bookmarks_cache

        bookmarks = await client.get_all_bookmarks()
        if self._allow_cache_reuse:
            self._karakeep_bookmarks_cache = bookmarks
        return bookmarks

    async def iter_bookmarks(
        self,
        client: KarakeepClientProtocol,
        *,
        correlation_id: str,
        page_size: int = BOOKMARK_PAGE_SIZE,
    ) -> AsyncIterator[tuple[str, KarakeepBookmark]]:
        cursor: str | None = None
        batches = 0
        count = 0
        completed = False

        try:
            while True:
                result = await client.get_bookmarks(limit=page_size, cursor=cursor)
                batches += 1

                for bookmark in result.bookmarks:
                    if not bookmark.url:
                        continue
                    normalized = normalize_url(bookmark.url) or bookmark.url
                    count += 1
                    yield normalized, bookmark

                if not result.next_cursor:
                    completed = True
                    break
                cursor = result.next_cursor
        finally:
            logger.info(
                "karakeep_bookmarks_iterated",
                extra={
                    "correlation_id": correlation_id,
                    "bookmark_count": count,
                    "batches": batches,
                    "stopped_early": not completed,
                },
            )

    async def _build_url_index(
        self,
        client: KarakeepClientProtocol,
        *,
        correlation_id: str,
    ) -> dict[str, KarakeepBookmark]:
        index: dict[str, KarakeepBookmark] = {}
        bookmarks: list[KarakeepBookmark] = []
        cursor: str | None = None
        batch_count = 0

        while True:
            result = await client.get_bookmarks(limit=BOOKMARK_PAGE_SIZE, cursor=cursor)
            batch_count += 1

            for bookmark in result.bookmarks:
                bookmarks.append(bookmark)
                if bookmark.url:
                    normalized = normalize_url(bookmark.url) or bookmark.url
                    index[normalized] = bookmark

            if not result.next_cursor:
                break
            cursor = result.next_cursor

        logger.info(
            "karakeep_url_index_built",
            extra={
                "correlation_id": correlation_id,
                "bookmark_count": len(index),
                "batches": batch_count,
            },
        )
        if self._allow_cache_reuse:
            self._karakeep_bookmarks_cache = bookmarks
        return index
