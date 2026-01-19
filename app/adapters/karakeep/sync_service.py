"""Karakeep sync service for bidirectional synchronization."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Protocol

from app.adapters.karakeep.client import KarakeepClient, KarakeepClientError
from app.adapters.karakeep.models import FullSyncResult, KarakeepBookmark, SyncResult
from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import normalize_url, url_hash_sha256
from app.utils.retry_utils import is_transient_error

logger = logging.getLogger(__name__)

# Tag names for status tracking (instead of using archived field)
TAG_BSR_READ = "bsr-read"
TAG_BSR_SYNCED = "bsr-synced"

# Legacy hash length for backward compatibility
LEGACY_HASH_LENGTH = 16
BOOKMARK_PAGE_SIZE = 100
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY_SECONDS = 0.5
DEFAULT_MAX_DELAY_SECONDS = 5.0
DEFAULT_BACKOFF_FACTOR = 2.0


class KarakeepClientProtocol(Protocol):
    async def health_check(self) -> bool: ...

    async def get_bookmarks(self, *, limit: int, cursor: str | None = None) -> Any: ...

    async def get_all_bookmarks(self) -> list[KarakeepBookmark]: ...

    async def create_bookmark(
        self, *, url: str, title: str | None, note: str | None
    ) -> KarakeepBookmark: ...

    async def update_bookmark(self, bookmark_id: str, *, favourited: bool) -> KarakeepBookmark: ...

    async def attach_tags(self, bookmark_id: str, tags: list[str]) -> KarakeepBookmark: ...

    async def detach_tag(self, bookmark_id: str, tag_id: str) -> None: ...

    async def delete_bookmark(self, bookmark_id: str) -> None: ...


class KarakeepClientFactory(Protocol):
    def __call__(
        self, api_url: str, api_key: str
    ) -> AbstractAsyncContextManager[KarakeepClientProtocol]: ...


class KarakeepSyncRepository(Protocol):
    async def async_get_synced_hashes_by_direction(self, sync_direction: str) -> set[str]: ...

    async def async_create_sync_record(
        self,
        *,
        bsr_summary_id: int | None = None,
        karakeep_bookmark_id: str | None = None,
        url_hash: str,
        sync_direction: str,
        synced_at: datetime | None = None,
        bsr_modified_at: datetime | None = None,
        karakeep_modified_at: datetime | None = None,
    ) -> int | None: ...

    async def async_get_summaries_for_sync(
        self, user_id: int | None = None
    ) -> list[dict[str, Any]]: ...

    async def async_get_existing_request_hashes(self) -> set[str]: ...

    async def async_create_request_from_karakeep(
        self,
        *,
        user_id: int,
        input_url: str,
        normalized_url: str | None,
        dedupe_hash: str | None,
    ) -> int: ...

    async def async_get_sync_stats(self) -> dict[str, Any]: ...

    async def async_get_crawl_result_title(self, request_id: int) -> str | None: ...

    async def async_get_synced_items_with_bookmark_and_summary(
        self,
    ) -> list[dict[str, Any]]: ...

    async def async_get_summary_by_id(self, summary_id: int) -> dict[str, Any] | None: ...

    async def async_update_summary_status(
        self,
        summary_id: int,
        is_read: bool | None = None,
        is_favorited: bool | None = None,
    ) -> None: ...

    async def async_update_sync_timestamps(
        self,
        sync_id: int,
        bsr_modified_at: datetime | None = None,
        karakeep_modified_at: datetime | None = None,
    ) -> None: ...


def _url_hash(url: str) -> str:
    """Generate consistent hash for URL deduplication.

    Uses full 64-char SHA256 for consistency with the rest of the codebase.
    """
    normalized = normalize_url(url) or url
    return url_hash_sha256(normalized)


def _check_hash_in_set(url_hash: str, hash_set: set[str]) -> bool:
    """Check if URL hash matches any hash in the set (handles legacy hashes).

    Args:
        url_hash: Full 64-char hash to check
        hash_set: Set of stored hashes (may contain legacy 16-char hashes)

    Returns:
        True if a match is found
    """
    # Fast path: check for exact match first
    if url_hash in hash_set:
        return True
    # Check for legacy hash match
    legacy_hash = url_hash[:LEGACY_HASH_LENGTH]
    return legacy_hash in hash_set


class KarakeepSyncService:
    """Bidirectional sync service between BSR and Karakeep."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        sync_tag: str = "bsr-synced",
        repository: KarakeepSyncRepository | None = None,
        client_factory: KarakeepClientFactory | None = None,
    ) -> None:
        """Initialize sync service.

        Args:
            api_url: Karakeep API URL
            api_key: Karakeep API key
            sync_tag: Tag to mark synced items
            repository: Repository adapter for database operations
            client_factory: Async context manager factory for Karakeep client
        """
        self.api_url = api_url
        self.api_key = api_key
        self.sync_tag = sync_tag
        self._repository = repository
        self._client_factory = client_factory or KarakeepClient
        self._karakeep_url_index_cache: dict[str, KarakeepBookmark] | None = None
        self._karakeep_bookmarks_cache: list[KarakeepBookmark] | None = None
        self._allow_cache_reuse = False

    def _require_repository(self) -> KarakeepSyncRepository:
        if not self._repository:
            raise RuntimeError("Repository not configured for sync service")
        return self._repository

    def _clear_karakeep_cache(self) -> None:
        self._karakeep_url_index_cache = None
        self._karakeep_bookmarks_cache = None

    @asynccontextmanager
    async def _cache_scope(self) -> Any:
        previous = self._allow_cache_reuse
        self._allow_cache_reuse = True
        self._clear_karakeep_cache()
        try:
            yield
        finally:
            self._allow_cache_reuse = previous

    async def _ensure_healthy(self, client: KarakeepClientProtocol, errors: list[str]) -> bool:
        if not await client.health_check():
            errors.append("Karakeep API health check failed")
            return False
        return True

    @staticmethod
    def _record_error(result: SyncResult, message: str, retryable: bool) -> None:
        if message not in result.errors:
            result.errors.append(message)
        if retryable:
            result.retryable_errors.append(message)
        else:
            result.permanent_errors.append(message)

    async def _retry_operation(
        self,
        func: Callable[[], Awaitable[Any]],
        *,
        operation_name: str,
        correlation_id: str,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY_SECONDS,
        max_delay: float = DEFAULT_MAX_DELAY_SECONDS,
    ) -> tuple[Any | None, bool, bool, Exception | None]:
        attempt = 0
        delay = base_delay
        last_error: Exception | None = None

        while True:
            try:
                return await func(), True, False, None
            except Exception as exc:
                last_error = exc
                retryable = is_transient_error(exc)
                if not retryable or attempt >= max_retries:
                    if retryable:
                        logger.warning(
                            "karakeep_retry_exhausted",
                            extra={
                                "correlation_id": correlation_id,
                                "operation": operation_name,
                                "attempts": attempt + 1,
                                "error": str(exc),
                            },
                        )
                    return None, False, retryable, last_error

                logger.debug(
                    "karakeep_retrying",
                    extra={
                        "correlation_id": correlation_id,
                        "operation": operation_name,
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "delay_seconds": min(delay, max_delay),
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(min(delay, max_delay))
                delay *= DEFAULT_BACKOFF_FACTOR
                attempt += 1

    async def _get_karakeep_url_index(
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

        index = await self._build_karakeep_url_index(client, correlation_id=correlation_id)
        if self._allow_cache_reuse:
            self._karakeep_url_index_cache = index
        return index

    async def _get_karakeep_bookmarks(
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

    async def _iter_karakeep_bookmarks(
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

    @staticmethod
    def _extract_summary_url(summary_data: dict[str, Any]) -> str | None:
        request_data = summary_data.get("request_data", {})
        return request_data.get("normalized_url")

    @staticmethod
    def _extract_summary_note(summary_data: dict[str, Any]) -> str | None:
        json_payload = summary_data.get("json_payload")
        if not json_payload:
            return None
        return json_payload.get("tldr") or json_payload.get("summary_250")

    @staticmethod
    def _extract_topic_tags(summary_data: dict[str, Any]) -> list[str]:
        json_payload = summary_data.get("json_payload")
        if not json_payload:
            return []
        topic_tags = json_payload.get("topic_tags", [])
        if len(topic_tags) > 5:
            logger.debug(
                "karakeep_truncating_tags",
                extra={"count": len(topic_tags), "limit": 5},
            )
        tags: list[str] = []
        for tag in topic_tags[:5]:
            clean_tag = tag.lstrip("#").strip()
            if clean_tag:
                tags.append(clean_tag)
        return tags

    @staticmethod
    def _build_base_tags(summary_data: dict[str, Any]) -> list[str]:
        tags = [TAG_BSR_SYNCED]
        if summary_data.get("is_read"):
            tags.append(TAG_BSR_READ)
        return tags

    async def _build_karakeep_url_index(
        self,
        client: KarakeepClientProtocol,
        *,
        correlation_id: str,
    ) -> dict[str, KarakeepBookmark]:
        """Build normalized URL -> bookmark index using batched pagination.

        This avoids loading all bookmarks into memory at once for large libraries.

        Args:
            client: Karakeep client

        Returns:
            Dict mapping normalized URLs to their bookmark objects
        """
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
                    # Normalize URL for consistent comparison
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

    async def sync_bsr_to_karakeep(
        self,
        user_id: int | None = None,
        limit: int | None = None,
    ) -> SyncResult:
        """Sync BSR summaries to Karakeep bookmarks.

        Args:
            user_id: Optional user ID filter
            limit: Maximum items to sync

        Returns:
            Sync result with counts
        """
        repository = self._require_repository()
        if not self._allow_cache_reuse:
            self._clear_karakeep_cache()
        correlation_id = generate_correlation_id()

        start_time = time.time()
        result = SyncResult(direction="bsr_to_karakeep")
        item_counters = {"tags_attached": 0, "favourites_updated": 0}
        logger.info(
            "karakeep_sync_bsr_to_karakeep_start",
            extra={"correlation_id": correlation_id, "user_id": user_id, "limit": limit},
        )

        try:
            async with self._client_factory(self.api_url, self.api_key) as client:
                # Health check before proceeding
                if not await self._ensure_healthy(client, result.errors):
                    self._record_error(result, "Karakeep API health check failed", retryable=True)
                    logger.error(
                        "karakeep_sync_health_check_failed",
                        extra={"correlation_id": correlation_id},
                    )
                    return result

                # Build normalized URL index for deduplication (batched for memory efficiency)
                karakeep_url_index = await self._get_karakeep_url_index(
                    client, correlation_id=correlation_id
                )

                # Get already synced hashes
                synced_hashes = await repository.async_get_synced_hashes_by_direction(
                    "bsr_to_karakeep"
                )

                # Get summaries eligible for sync
                summaries_data = await repository.async_get_summaries_for_sync(user_id=user_id)

                summaries_to_sync: list[dict[str, Any]] = []
                for summary_data in summaries_data:
                    url = self._extract_summary_url(summary_data)
                    if not url:
                        continue
                    url_hash = _url_hash(url)

                    # Skip if already synced (handles legacy hash format)
                    if _check_hash_in_set(url_hash, synced_hashes):
                        result.items_skipped += 1
                        continue

                    # Check if URL exists in Karakeep (using normalized comparison)
                    if url in karakeep_url_index:
                        # Already in Karakeep, mark as synced
                        existing_bookmark = karakeep_url_index[url]
                        await repository.async_create_sync_record(
                            bsr_summary_id=summary_data.get("id"),
                            karakeep_bookmark_id=existing_bookmark.id,
                            url_hash=url_hash,
                            sync_direction="bsr_to_karakeep",
                            synced_at=datetime.now(UTC),
                            bsr_modified_at=summary_data.get("updated_at"),
                            karakeep_modified_at=existing_bookmark.modified_at,
                        )
                        result.items_skipped += 1
                        synced_hashes.add(url_hash)
                        continue

                    summary_data["_sync_url_hash"] = url_hash
                    summaries_to_sync.append(summary_data)
                    if limit and len(summaries_to_sync) >= limit:
                        break

                # Sync each summary to Karakeep
                for summary_data in summaries_to_sync:
                    try:
                        non_fatal_errors = await self._sync_summary_to_karakeep(
                            client,
                            repository,
                            summary_data,
                            correlation_id=correlation_id,
                            counters=item_counters,
                        )
                        result.items_synced += 1
                        url_hash = summary_data.get("_sync_url_hash")
                        if isinstance(url_hash, str):
                            synced_hashes.add(url_hash)
                        for message, retryable in non_fatal_errors:
                            self._record_error(result, message, retryable)
                    except Exception as e:
                        result.items_failed += 1
                        error_message = f"Failed to sync summary {summary_data.get('id')}: {e}"
                        self._record_error(result, error_message, is_transient_error(e))
                        logger.warning(
                            "karakeep_sync_item_failed",
                            extra={
                                "correlation_id": correlation_id,
                                "summary_id": summary_data.get("id"),
                                "error": str(e),
                            },
                        )

        except KarakeepClientError as e:
            error_message = f"Karakeep client error: {e}"
            self._record_error(result, error_message, is_transient_error(e))
            logger.error(
                "karakeep_sync_client_error",
                extra={"correlation_id": correlation_id, "error": str(e)},
            )
        except Exception as e:
            error_message = f"Unexpected error: {e}"
            self._record_error(result, error_message, is_transient_error(e))
            logger.exception(
                "karakeep_sync_unexpected_error",
                extra={"correlation_id": correlation_id},
            )

        result.duration_seconds = time.time() - start_time
        logger.info(
            "karakeep_sync_bsr_to_karakeep_complete",
            extra={
                "correlation_id": correlation_id,
                "synced": result.items_synced,
                "skipped": result.items_skipped,
                "failed": result.items_failed,
                "tags_attached": item_counters["tags_attached"],
                "favourites_updated": item_counters["favourites_updated"],
                "duration": result.duration_seconds,
            },
        )
        return result

    async def _sync_summary_to_karakeep(
        self,
        client: KarakeepClientProtocol,
        repository: KarakeepSyncRepository,
        summary_data: dict[str, Any],
        *,
        correlation_id: str,
        counters: dict[str, int] | None = None,
    ) -> list[tuple[str, bool]]:
        """Sync a single BSR summary to Karakeep.

        Args:
            client: Karakeep client
            summary_data: Summary dict with request_data

        Raises:
            RuntimeError: If bookmark creation or sync record persistence fails
        """
        non_fatal_errors: list[tuple[str, bool]] = []
        url = self._extract_summary_url(summary_data)
        if not url:
            return non_fatal_errors

        summary_id = summary_data.get("id")
        request_id = summary_data.get("request_data", {}).get("id")

        # Get metadata
        title = None
        note = None

        # Try to get title from crawl result
        if request_id:
            try:
                title = await repository.async_get_crawl_result_title(request_id)
            except Exception as e:
                logger.warning(
                    "karakeep_crawl_result_fetch_failed",
                    extra={
                        "correlation_id": correlation_id,
                        "request_id": request_id,
                        "error": str(e),
                    },
                )

        # Get summary text for note
        note = self._extract_summary_note(summary_data)

        # Create bookmark
        bookmark, created, _, error = await self._retry_operation(
            lambda: client.create_bookmark(url=url, title=title, note=note),
            operation_name="create_bookmark",
            correlation_id=correlation_id,
        )
        if not created or not bookmark:
            raise RuntimeError(f"Failed to create bookmark for summary {summary_id}: {error}")
        last_karakeep_modified_at = bookmark.modified_at

        # Build tags list
        tags = self._build_base_tags(summary_data)

        # Persist sync record before tag updates for idempotency
        sync_id = await repository.async_create_sync_record(
            bsr_summary_id=summary_id,
            karakeep_bookmark_id=bookmark.id,
            url_hash=_url_hash(url),
            sync_direction="bsr_to_karakeep",
            synced_at=datetime.now(UTC),
            bsr_modified_at=summary_data.get("updated_at"),
            karakeep_modified_at=bookmark.modified_at,
        )

        if sync_id is None:
            # Duplicate sync record - another sync beat us to it
            # Delete the bookmark we just created to avoid orphans
            logger.warning(
                "karakeep_sync_record_duplicate_cleanup",
                extra={
                    "correlation_id": correlation_id,
                    "bookmark_id": bookmark.id,
                    "summary_id": summary_id,
                },
            )
            try:
                await client.delete_bookmark(bookmark.id)
            except Exception as cleanup_err:
                logger.error(
                    "karakeep_duplicate_cleanup_failed",
                    extra={
                        "correlation_id": correlation_id,
                        "bookmark_id": bookmark.id,
                        "error": str(cleanup_err),
                    },
                )
            raise RuntimeError("Duplicate sync record detected")

        # Sync favorite status (favourited has correct semantics)
        if summary_data.get("is_favorited"):
            updated_bookmark, success, fav_retryable, fav_error = await self._retry_operation(
                lambda: client.update_bookmark(bookmark.id, favourited=True),
                operation_name="update_bookmark_favourite",
                correlation_id=correlation_id,
            )
            if not success:
                message = f"Failed to update favourite for summary {summary_id}: {fav_error}"
                non_fatal_errors.append((message, fav_retryable))
                logger.warning(
                    "karakeep_update_favourite_failed",
                    extra={
                        "correlation_id": correlation_id,
                        "bookmark_id": bookmark.id,
                        "error": str(fav_error),
                    },
                )
            else:
                if isinstance(updated_bookmark, KarakeepBookmark) and updated_bookmark.modified_at:
                    last_karakeep_modified_at = updated_bookmark.modified_at
                if counters is not None:
                    counters["favourites_updated"] = counters.get("favourites_updated", 0) + 1

        # Add topic tags from summary
        tags.extend(self._extract_topic_tags(summary_data))

        # Attach tags
        if tags:
            updated_bookmark, success, tag_retryable, tag_error = await self._retry_operation(
                lambda: client.attach_tags(bookmark.id, tags),
                operation_name="attach_tags",
                correlation_id=correlation_id,
            )
            if not success:
                message = f"Failed to attach tags for summary {summary_id}: {tag_error}"
                non_fatal_errors.append((message, tag_retryable))
                logger.warning(
                    "karakeep_attach_tags_failed",
                    extra={
                        "correlation_id": correlation_id,
                        "bookmark_id": bookmark.id,
                        "error": str(tag_error),
                    },
                )
            else:
                if isinstance(updated_bookmark, KarakeepBookmark) and updated_bookmark.modified_at:
                    last_karakeep_modified_at = updated_bookmark.modified_at
                if counters is not None:
                    counters["tags_attached"] = counters.get("tags_attached", 0) + len(tags)

        if last_karakeep_modified_at and last_karakeep_modified_at != bookmark.modified_at:
            await repository.async_update_sync_timestamps(
                sync_id,
                karakeep_modified_at=last_karakeep_modified_at,
            )

        return non_fatal_errors

    async def sync_karakeep_to_bsr(
        self,
        user_id: int,
        limit: int | None = None,
    ) -> SyncResult:
        """Sync Karakeep bookmarks to BSR for summarization.

        Args:
            user_id: BSR user ID to associate requests with
            limit: Maximum items to sync

        Returns:
            Sync result with counts
        """
        repository = self._require_repository()
        if not self._allow_cache_reuse:
            self._clear_karakeep_cache()
        correlation_id = generate_correlation_id()

        start_time = time.time()
        result = SyncResult(direction="karakeep_to_bsr")
        logger.info(
            "karakeep_sync_karakeep_to_bsr_start",
            extra={"correlation_id": correlation_id, "user_id": user_id, "limit": limit},
        )

        try:
            async with self._client_factory(self.api_url, self.api_key) as client:
                # Health check before proceeding
                if not await self._ensure_healthy(client, result.errors):
                    self._record_error(result, "Karakeep API health check failed", retryable=True)
                    logger.error(
                        "karakeep_sync_health_check_failed",
                        extra={"correlation_id": correlation_id},
                    )
                    return result

                # Get already synced hashes
                synced_hashes = await repository.async_get_synced_hashes_by_direction(
                    "karakeep_to_bsr"
                )

                # Get existing BSR URLs (via dedupe_hash)
                existing_hashes = await repository.async_get_existing_request_hashes()

                async def process_bookmark(normalized_url: str, bookmark: KarakeepBookmark) -> bool:
                    url_hash = _url_hash(bookmark.url or "")

                    # Skip if already synced from Karakeep (handles legacy hash format)
                    if _check_hash_in_set(url_hash, synced_hashes):
                        result.items_skipped += 1
                        return False

                    # Check if already exists in BSR using full hash
                    dedupe = url_hash_sha256(normalized_url)
                    if dedupe in existing_hashes:
                        # Mark as synced since it exists
                        await repository.async_create_sync_record(
                            karakeep_bookmark_id=bookmark.id,
                            url_hash=url_hash,
                            sync_direction="karakeep_to_bsr",
                            synced_at=datetime.now(UTC),
                            karakeep_modified_at=bookmark.modified_at,
                        )
                        result.items_skipped += 1
                        synced_hashes.add(url_hash)
                        return False

                    try:
                        await self._submit_url_to_bsr(
                            repository,
                            bookmark,
                            user_id,
                            correlation_id=correlation_id,
                        )
                        result.items_synced += 1
                        synced_hashes.add(url_hash)
                        existing_hashes.add(dedupe)
                    except Exception as e:
                        result.items_failed += 1
                        error_message = f"Failed to sync bookmark {bookmark.id}: {e}"
                        self._record_error(result, error_message, is_transient_error(e))
                        logger.warning(
                            "karakeep_sync_bookmark_failed",
                            extra={
                                "correlation_id": correlation_id,
                                "bookmark_id": bookmark.id,
                                "error": str(e),
                            },
                        )

                    return bool(limit and result.items_synced >= limit)

                # Submit URLs to BSR for processing with early exit
                if self._allow_cache_reuse and self._karakeep_bookmarks_cache is not None:
                    for bookmark in self._karakeep_bookmarks_cache:
                        if not bookmark.url:
                            continue
                        normalized_url = normalize_url(bookmark.url) or bookmark.url
                        if await process_bookmark(normalized_url, bookmark):
                            break
                else:
                    async for normalized_url, bookmark in self._iter_karakeep_bookmarks(
                        client, correlation_id=correlation_id
                    ):
                        if await process_bookmark(normalized_url, bookmark):
                            break

        except KarakeepClientError as e:
            error_message = f"Karakeep client error: {e}"
            self._record_error(result, error_message, is_transient_error(e))
            logger.error(
                "karakeep_sync_client_error",
                extra={"correlation_id": correlation_id, "error": str(e)},
            )
        except Exception as e:
            error_message = f"Unexpected error: {e}"
            self._record_error(result, error_message, is_transient_error(e))
            logger.exception(
                "karakeep_sync_unexpected_error",
                extra={"correlation_id": correlation_id},
            )

        result.duration_seconds = time.time() - start_time
        logger.info(
            "karakeep_sync_karakeep_to_bsr_complete",
            extra={
                "correlation_id": correlation_id,
                "synced": result.items_synced,
                "skipped": result.items_skipped,
                "failed": result.items_failed,
                "duration": result.duration_seconds,
            },
        )
        return result

    async def _submit_url_to_bsr(
        self,
        repository: KarakeepSyncRepository,
        bookmark: KarakeepBookmark,
        user_id: int,
        *,
        correlation_id: str | None = None,
    ) -> None:
        """Submit a Karakeep bookmark URL to BSR for processing.

        Args:
            bookmark: Karakeep bookmark
            user_id: BSR user ID
        """
        url = bookmark.url
        if not url:
            return

        normalized = normalize_url(url)
        dedupe_hash = url_hash_sha256(normalized) if normalized else None

        # Create BSR request
        await repository.async_create_request_from_karakeep(
            user_id=user_id,
            input_url=url,
            normalized_url=normalized,
            dedupe_hash=dedupe_hash,
        )

        # Mark as synced
        sync_id = await repository.async_create_sync_record(
            bsr_summary_id=None,  # Will be set when summary is created
            karakeep_bookmark_id=bookmark.id,
            url_hash=_url_hash(url),
            sync_direction="karakeep_to_bsr",
            synced_at=datetime.now(UTC),
            karakeep_modified_at=bookmark.modified_at,
        )

        if sync_id is None:
            # Duplicate - another sync beat us to it
            logger.warning(
                "karakeep_submit_url_duplicate",
                extra={
                    "correlation_id": correlation_id,
                    "bookmark_id": bookmark.id,
                    "url": url,
                },
            )
            raise RuntimeError("Duplicate sync record detected")

        logger.info(
            "karakeep_url_submitted_to_bsr",
            extra={
                "correlation_id": correlation_id,
                "bookmark_id": bookmark.id,
                "url": url,
            },
        )

    async def run_full_sync(
        self,
        user_id: int | None = None,
        limit: int | None = None,
    ) -> FullSyncResult:
        """Run bidirectional sync.

        Args:
            user_id: User ID for Karakeep->BSR sync (required)
            limit: Maximum items per direction

        Returns:
            Full sync result
        """
        start_time = time.time()
        correlation_id = generate_correlation_id()

        async with self._cache_scope():
            # BSR -> Karakeep
            bsr_result = await self.sync_bsr_to_karakeep(user_id=user_id, limit=limit)

            # Karakeep -> BSR (requires user_id)
            if user_id:
                karakeep_result = await self.sync_karakeep_to_bsr(user_id=user_id, limit=limit)
            else:
                karakeep_result = SyncResult(direction="karakeep_to_bsr")
                karakeep_result.errors.append("Skipped: user_id required for Karakeep->BSR sync")

            # Sync status updates for already-synced items
            status_result = await self.sync_status_updates()

        total_duration = time.time() - start_time
        result = FullSyncResult(
            bsr_to_karakeep=bsr_result,
            karakeep_to_bsr=karakeep_result,
            total_synced=bsr_result.items_synced + karakeep_result.items_synced,
            total_duration_seconds=total_duration,
        )

        logger.info(
            "karakeep_full_sync_complete",
            extra={
                "correlation_id": correlation_id,
                "bsr_to_karakeep": bsr_result.items_synced,
                "karakeep_to_bsr": karakeep_result.items_synced,
                "status_updates_bsr_to_kk": status_result["bsr_to_karakeep_updated"],
                "status_updates_kk_to_bsr": status_result["karakeep_to_bsr_updated"],
                "total_duration": total_duration,
            },
        )

        return result

    async def get_sync_status(self) -> dict[str, Any]:
        """Get current sync status and stats.

        Returns:
            Dict with sync statistics
        """
        repository = self._require_repository()
        return await repository.async_get_sync_stats()

    async def preview_sync(
        self,
        user_id: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Preview what would be synced without making changes (dry-run).

        Args:
            user_id: Optional user ID filter
            limit: Maximum items to preview per direction

        Returns:
            Dict with preview information
        """
        repository = self._require_repository()
        if not self._allow_cache_reuse:
            self._clear_karakeep_cache()
        correlation_id = generate_correlation_id()

        preview: dict[str, Any] = {
            "bsr_to_karakeep": {
                "would_sync": [],
                "would_skip": 0,
                "already_exists_in_karakeep": [],
            },
            "karakeep_to_bsr": {
                "would_sync": [],
                "would_skip": 0,
                "already_exists_in_bsr": [],
            },
            "errors": [],
        }
        logger.info(
            "karakeep_sync_preview_start",
            extra={"correlation_id": correlation_id, "user_id": user_id, "limit": limit},
        )

        try:
            async with self._client_factory(self.api_url, self.api_key) as client:
                # Health check
                if not await self._ensure_healthy(client, preview["errors"]):
                    return preview

                # Build normalized URL index (batched for memory efficiency)
                karakeep_url_index = await self._get_karakeep_url_index(
                    client, correlation_id=correlation_id
                )

                # Get already synced hashes
                synced_hashes_bsr = await repository.async_get_synced_hashes_by_direction(
                    "bsr_to_karakeep"
                )
                synced_hashes_kk = await repository.async_get_synced_hashes_by_direction(
                    "karakeep_to_bsr"
                )

                # BSR -> Karakeep preview
                summaries_data = await repository.async_get_summaries_for_sync(user_id=user_id)

                count = 0
                for summary_data in summaries_data:
                    if limit and count >= limit:
                        break
                    url = self._extract_summary_url(summary_data)
                    if not url:
                        continue
                    url_hash = _url_hash(url)

                    # Check if already synced (handles legacy hash format)
                    if _check_hash_in_set(url_hash, synced_hashes_bsr):
                        preview["bsr_to_karakeep"]["would_skip"] += 1
                        continue

                    # Check if URL exists in Karakeep (using normalized comparison)
                    if url in karakeep_url_index:
                        preview["bsr_to_karakeep"]["already_exists_in_karakeep"].append(
                            {
                                "summary_id": summary_data.get("id"),
                                "url": url,
                                "karakeep_id": karakeep_url_index[url].id,
                            }
                        )
                        preview["bsr_to_karakeep"]["would_skip"] += 1
                        continue

                    # Would be synced
                    title = None
                    json_payload = summary_data.get("json_payload")
                    if json_payload:
                        title = json_payload.get("summary_250", "")[:100]
                    preview["bsr_to_karakeep"]["would_sync"].append(
                        {
                            "summary_id": summary_data.get("id"),
                            "url": url,
                            "title": title,
                            "is_read": summary_data.get("is_read"),
                            "is_favorited": summary_data.get("is_favorited"),
                        }
                    )
                    count += 1

                # Karakeep -> BSR preview
                existing_hashes = await repository.async_get_existing_request_hashes()

                count = 0

                async def process_preview_bookmark(
                    normalized_url: str, bookmark: KarakeepBookmark
                ) -> bool:
                    nonlocal count
                    url_hash = _url_hash(bookmark.url or "")

                    # Check if already synced (handles legacy hash format)
                    if _check_hash_in_set(url_hash, synced_hashes_kk):
                        preview["karakeep_to_bsr"]["would_skip"] += 1
                        return False

                    # Check if already exists in BSR using full hash
                    dedupe = url_hash_sha256(normalized_url)
                    if dedupe in existing_hashes:
                        preview["karakeep_to_bsr"]["already_exists_in_bsr"].append(
                            {
                                "karakeep_id": bookmark.id,
                                "url": bookmark.url,
                            }
                        )
                        preview["karakeep_to_bsr"]["would_skip"] += 1
                        return False

                    # Would be synced
                    preview["karakeep_to_bsr"]["would_sync"].append(
                        {
                            "karakeep_id": bookmark.id,
                            "url": bookmark.url,
                            "title": bookmark.title,
                            "archived": bookmark.archived,
                            "favourited": bookmark.favourited,
                        }
                    )
                    count += 1
                    return bool(limit and count >= limit)

                if self._allow_cache_reuse and self._karakeep_bookmarks_cache is not None:
                    for bookmark in self._karakeep_bookmarks_cache:
                        if not bookmark.url:
                            continue
                        normalized_url = normalize_url(bookmark.url) or bookmark.url
                        if await process_preview_bookmark(normalized_url, bookmark):
                            break
                else:
                    async for normalized_url, bookmark in self._iter_karakeep_bookmarks(
                        client, correlation_id=correlation_id
                    ):
                        if await process_preview_bookmark(normalized_url, bookmark):
                            break

        except KarakeepClientError as e:
            preview["errors"].append(f"Karakeep client error: {e}")
        except Exception as e:
            preview["errors"].append(f"Unexpected error: {e}")

        return preview

    async def sync_status_updates(self) -> dict[str, int | list[str]]:
        """Sync read/favorite status for already-synced items.

        This updates:
        - BSR is_read -> Karakeep 'bsr-read' tag
        - BSR is_favorited -> Karakeep favourited
        - Karakeep 'bsr-read' tag -> BSR is_read
        - Karakeep favourited -> BSR is_favorited

        Uses timestamp-based conflict resolution when both have been modified.

        Returns:
            Dict with update counts and tag/favourite update totals
        """
        repository = self._require_repository()
        if not self._allow_cache_reuse:
            self._clear_karakeep_cache()
        correlation_id = generate_correlation_id()

        bsr_to_kk_updated = 0
        kk_to_bsr_updated = 0
        tags_added = 0
        tags_removed = 0
        favourites_updated = 0
        errors: list[str] = []
        logger.info(
            "karakeep_status_sync_start",
            extra={"correlation_id": correlation_id},
        )

        try:
            async with self._client_factory(self.api_url, self.api_key) as client:
                # Health check
                if not await self._ensure_healthy(client, errors):
                    logger.error(
                        "karakeep_status_sync_health_check_failed",
                        extra={"correlation_id": correlation_id},
                    )
                    return {
                        "bsr_to_karakeep_updated": 0,
                        "karakeep_to_bsr_updated": 0,
                        "tags_added": 0,
                        "tags_removed": 0,
                        "favourites_updated": 0,
                        "errors": errors,
                    }

                # Get all synced items that have Karakeep bookmark IDs and summary IDs
                synced_items = await repository.async_get_synced_items_with_bookmark_and_summary()
                if not synced_items:
                    logger.info(
                        "karakeep_status_sync_no_items",
                        extra={"correlation_id": correlation_id},
                    )
                    return {
                        "bsr_to_karakeep_updated": 0,
                        "karakeep_to_bsr_updated": 0,
                        "tags_added": 0,
                        "tags_removed": 0,
                        "favourites_updated": 0,
                        "errors": errors,
                    }

                # Get all Karakeep bookmarks for status lookup
                karakeep_bookmarks = await self._get_karakeep_bookmarks(
                    client, correlation_id=correlation_id
                )
                karakeep_by_id = {b.id: b for b in karakeep_bookmarks}

                for sync_record in synced_items:
                    try:
                        summary_id = sync_record.get("bsr_summary")
                        bookmark_id = sync_record.get("karakeep_bookmark_id")
                        sync_id = sync_record.get("id")

                        if not summary_id or not bookmark_id or not sync_id:
                            continue

                        # Get BSR summary
                        summary_data = await repository.async_get_summary_by_id(summary_id)
                        if not summary_data:
                            continue

                        # Get Karakeep bookmark
                        bookmark = karakeep_by_id.get(bookmark_id)
                        if not bookmark:
                            continue

                        # Determine read status from Karakeep tags (not archived field)
                        kk_has_read_tag = any(t.name == TAG_BSR_READ for t in (bookmark.tags or []))
                        kk_fav = bookmark.favourited

                        bsr_read = summary_data.get("is_read", False)
                        bsr_fav = summary_data.get("is_favorited", False)

                        # Determine source of truth based on sync direction and timestamps
                        bsr_is_source = sync_record.get("sync_direction") == "bsr_to_karakeep"
                        summary_updated_at = summary_data.get("updated_at")
                        bookmark_updated_at = bookmark.modified_at
                        bsr_modified_at = sync_record.get("bsr_modified_at")
                        karakeep_modified_at = sync_record.get("karakeep_modified_at")

                        # Prefer actual modified timestamps when available
                        if summary_updated_at and bookmark_updated_at:
                            if summary_updated_at > bookmark_updated_at:
                                bsr_is_source = True
                            elif bookmark_updated_at > summary_updated_at:
                                bsr_is_source = False
                        elif summary_updated_at and bsr_modified_at:
                            if summary_updated_at > bsr_modified_at:
                                bsr_is_source = True
                        elif bookmark_updated_at and karakeep_modified_at:
                            if bookmark_updated_at > karakeep_modified_at:
                                bsr_is_source = False

                        if bsr_is_source:
                            # Sync BSR -> Karakeep
                            needs_update = False
                            tags_to_add: list[str] = []
                            tags_to_remove: list[str] = []
                            last_karakeep_modified_at = bookmark.modified_at

                            # Handle read status via tags
                            if bsr_read and not kk_has_read_tag:
                                tags_to_add.append(TAG_BSR_READ)
                                needs_update = True
                            elif not bsr_read and kk_has_read_tag:
                                # Find and remove the tag
                                for tag in bookmark.tags or []:
                                    if tag.name == TAG_BSR_READ:
                                        tags_to_remove.append(tag.id)
                                        needs_update = True
                                        break

                            # Handle favourite status
                            if bsr_fav != kk_fav:
                                updated, success, retryable, error = await self._retry_operation(
                                    lambda: client.update_bookmark(
                                        bookmark.id,
                                        favourited=bsr_fav,
                                    ),
                                    operation_name="update_bookmark_favourite",
                                    correlation_id=correlation_id,
                                )
                                if success:
                                    favourites_updated += 1
                                    needs_update = True
                                    if updated and updated.modified_at:
                                        last_karakeep_modified_at = updated.modified_at
                                else:
                                    errors.append(
                                        f"Failed to update favourite for bookmark {bookmark.id}: {error}"
                                    )
                                    logger.warning(
                                        "karakeep_status_update_favourite_failed",
                                        extra={
                                            "correlation_id": correlation_id,
                                            "bookmark_id": bookmark.id,
                                            "error": str(error),
                                            "retryable": retryable,
                                        },
                                    )

                            # Apply tag changes
                            if tags_to_add:
                                updated, success, retryable, error = await self._retry_operation(
                                    lambda: client.attach_tags(bookmark.id, tags_to_add),
                                    operation_name="attach_tags",
                                    correlation_id=correlation_id,
                                )
                                if success:
                                    tags_added += len(tags_to_add)
                                    needs_update = True
                                    if updated and updated.modified_at:
                                        last_karakeep_modified_at = updated.modified_at
                                else:
                                    errors.append(
                                        f"Failed to attach tags for bookmark {bookmark.id}: {error}"
                                    )
                                    logger.warning(
                                        "karakeep_status_attach_tags_failed",
                                        extra={
                                            "correlation_id": correlation_id,
                                            "bookmark_id": bookmark.id,
                                            "error": str(error),
                                            "retryable": retryable,
                                        },
                                    )
                            for tag_id in tags_to_remove:
                                _, success, retryable, error = await self._retry_operation(
                                    lambda: client.detach_tag(bookmark.id, tag_id),
                                    operation_name="detach_tag",
                                    correlation_id=correlation_id,
                                )
                                if success:
                                    tags_removed += 1
                                    needs_update = True
                                    last_karakeep_modified_at = datetime.now(UTC)
                                else:
                                    errors.append(
                                        f"Failed to detach tag for bookmark {bookmark.id}: {error}"
                                    )
                                    logger.warning(
                                        "karakeep_status_detach_tag_failed",
                                        extra={
                                            "correlation_id": correlation_id,
                                            "bookmark_id": bookmark.id,
                                            "error": str(error),
                                            "retryable": retryable,
                                        },
                                    )

                            if needs_update:
                                # Update sync record timestamps
                                await repository.async_update_sync_timestamps(
                                    sync_id,
                                    bsr_modified_at=summary_data.get("updated_at"),
                                    karakeep_modified_at=last_karakeep_modified_at
                                    or datetime.now(UTC),
                                )
                                bsr_to_kk_updated += 1
                                logger.debug(
                                    "karakeep_status_synced_to_karakeep",
                                    extra={
                                        "correlation_id": correlation_id,
                                        "bookmark_id": bookmark.id,
                                        "read_tag": bsr_read,
                                        "favourited": bsr_fav,
                                    },
                                )

                        # Sync Karakeep -> BSR
                        elif kk_has_read_tag != bsr_read or kk_fav != bsr_fav:
                            await repository.async_update_summary_status(
                                summary_id,
                                is_read=kk_has_read_tag,
                                is_favorited=kk_fav,
                            )

                            # Update sync record timestamps
                            await repository.async_update_sync_timestamps(
                                sync_id,
                                bsr_modified_at=datetime.now(UTC),
                                karakeep_modified_at=bookmark.modified_at or datetime.now(UTC),
                            )

                            kk_to_bsr_updated += 1
                            logger.debug(
                                "karakeep_status_synced_to_bsr",
                                extra={
                                    "correlation_id": correlation_id,
                                    "summary_id": summary_id,
                                    "is_read": kk_has_read_tag,
                                    "is_favorited": kk_fav,
                                },
                            )

                    except Exception as e:
                        error_msg = f"Failed to sync status for {sync_record.get('id')}: {e}"
                        errors.append(error_msg)
                        logger.warning(
                            "karakeep_status_sync_item_failed",
                            extra={
                                "correlation_id": correlation_id,
                                "sync_id": sync_record.get("id"),
                                "error": str(e),
                            },
                        )

        except Exception as e:
            errors.append(f"Status sync failed: {e}")
            logger.exception(
                "karakeep_status_sync_failed",
                extra={"correlation_id": correlation_id},
            )

        logger.info(
            "karakeep_status_sync_complete",
            extra={
                "correlation_id": correlation_id,
                "bsr_to_karakeep": bsr_to_kk_updated,
                "karakeep_to_bsr": kk_to_bsr_updated,
                "tags_added": tags_added,
                "tags_removed": tags_removed,
                "favourites_updated": favourites_updated,
                "errors": len(errors),
            },
        )

        return {
            "bsr_to_karakeep_updated": bsr_to_kk_updated,
            "karakeep_to_bsr_updated": kk_to_bsr_updated,
            "tags_added": tags_added,
            "tags_removed": tags_removed,
            "favourites_updated": favourites_updated,
            "errors": errors,
        }
