"""Karakeep sync service for bidirectional synchronization."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.adapters.karakeep.client import KarakeepClient, KarakeepClientError
from app.adapters.karakeep.models import FullSyncResult, KarakeepBookmark, SyncResult
from app.core.url_utils import normalize_url, url_hash_sha256

if TYPE_CHECKING:
    from app.infrastructure.persistence.sqlite.repositories.karakeep_sync_repository import (
        SqliteKarakeepSyncRepositoryAdapter,
    )

logger = logging.getLogger(__name__)

# Tag names for status tracking (instead of using archived field)
TAG_BSR_READ = "bsr-read"
TAG_BSR_SYNCED = "bsr-synced"

# Legacy hash length for backward compatibility
LEGACY_HASH_LENGTH = 16


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
        repository: SqliteKarakeepSyncRepositoryAdapter | None = None,
    ) -> None:
        """Initialize sync service.

        Args:
            api_url: Karakeep API URL
            api_key: Karakeep API key
            sync_tag: Tag to mark synced items
            repository: Repository adapter for database operations
        """
        self.api_url = api_url
        self.api_key = api_key
        self.sync_tag = sync_tag
        self._repository = repository

    async def _build_karakeep_url_index(
        self,
        client: KarakeepClient,
    ) -> dict[str, KarakeepBookmark]:
        """Build normalized URL -> bookmark index using batched pagination.

        This avoids loading all bookmarks into memory at once for large libraries.

        Args:
            client: Karakeep client

        Returns:
            Dict mapping normalized URLs to their bookmark objects
        """
        index: dict[str, KarakeepBookmark] = {}
        cursor: str | None = None
        batch_count = 0

        while True:
            result = await client.get_bookmarks(limit=100, cursor=cursor)
            batch_count += 1

            for bookmark in result.bookmarks:
                if bookmark.url:
                    # Normalize URL for consistent comparison
                    normalized = normalize_url(bookmark.url) or bookmark.url
                    index[normalized] = bookmark

            if not result.next_cursor:
                break
            cursor = result.next_cursor

        logger.info(
            "karakeep_url_index_built",
            extra={"bookmark_count": len(index), "batches": batch_count},
        )
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
        if not self._repository:
            raise RuntimeError("Repository not configured for sync service")

        start_time = time.time()
        result = SyncResult(direction="bsr_to_karakeep")

        try:
            async with KarakeepClient(self.api_url, self.api_key) as client:
                # Health check before proceeding
                if not await client.health_check():
                    result.errors.append("Karakeep API health check failed")
                    logger.error("karakeep_sync_health_check_failed")
                    return result

                # Build normalized URL index for deduplication (batched for memory efficiency)
                karakeep_url_index = await self._build_karakeep_url_index(client)

                # Get already synced hashes
                synced_hashes = await self._repository.async_get_synced_hashes_by_direction(
                    "bsr_to_karakeep"
                )

                # Get summaries eligible for sync
                summaries_data = await self._repository.async_get_summaries_for_sync(
                    user_id=user_id
                )

                summaries_to_sync: list[dict[str, Any]] = []
                for summary_data in summaries_data:
                    request_data = summary_data.get("request_data", {})
                    url = request_data.get("normalized_url")
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
                        await self._repository.async_create_sync_record(
                            bsr_summary_id=summary_data.get("id"),
                            karakeep_bookmark_id=existing_bookmark.id,
                            url_hash=url_hash,
                            sync_direction="bsr_to_karakeep",
                            synced_at=datetime.now(UTC),
                            bsr_modified_at=summary_data.get("updated_at"),
                        )
                        result.items_skipped += 1
                        continue

                    summaries_to_sync.append(summary_data)
                    if limit and len(summaries_to_sync) >= limit:
                        break

                # Sync each summary to Karakeep
                for summary_data in summaries_to_sync:
                    try:
                        await self._sync_summary_to_karakeep(client, summary_data)
                        result.items_synced += 1
                    except Exception as e:
                        result.items_failed += 1
                        result.errors.append(
                            f"Failed to sync summary {summary_data.get('id')}: {e}"
                        )
                        logger.warning(
                            "karakeep_sync_item_failed",
                            extra={"summary_id": summary_data.get("id"), "error": str(e)},
                        )

        except KarakeepClientError as e:
            result.errors.append(f"Karakeep client error: {e}")
            logger.error("karakeep_sync_client_error", extra={"error": str(e)})
        except Exception as e:
            result.errors.append(f"Unexpected error: {e}")
            logger.exception("karakeep_sync_unexpected_error")

        result.duration_seconds = time.time() - start_time
        logger.info(
            "karakeep_sync_bsr_to_karakeep_complete",
            extra={
                "synced": result.items_synced,
                "skipped": result.items_skipped,
                "failed": result.items_failed,
                "duration": result.duration_seconds,
            },
        )
        return result

    async def _sync_summary_to_karakeep(
        self,
        client: KarakeepClient,
        summary_data: dict[str, Any],
    ) -> None:
        """Sync a single BSR summary to Karakeep.

        Args:
            client: Karakeep client
            summary_data: Summary dict with request_data

        Raises:
            Exception: If sync fails after cleanup attempt
        """
        if not self._repository:
            raise RuntimeError("Repository not configured for sync service")

        request_data = summary_data.get("request_data", {})
        url = request_data.get("normalized_url")
        if not url:
            return

        summary_id = summary_data.get("id")
        request_id = request_data.get("id")

        # Get metadata
        title = None
        note = None

        # Try to get title from crawl result
        if request_id:
            try:
                title = await self._repository.async_get_crawl_result_title(request_id)
            except Exception as e:
                logger.warning(
                    "karakeep_crawl_result_fetch_failed",
                    extra={"request_id": request_id, "error": str(e)},
                )

        # Get summary text for note
        json_payload = summary_data.get("json_payload")
        if json_payload:
            tldr = json_payload.get("tldr")
            summary_250 = json_payload.get("summary_250")
            note = tldr or summary_250

        # Create bookmark
        bookmark = await client.create_bookmark(url=url, title=title, note=note)

        # Build tags list
        tags = [TAG_BSR_SYNCED]

        # Use 'bsr-read' tag for read status instead of archived field
        if summary_data.get("is_read"):
            tags.append(TAG_BSR_READ)

        # Sync favorite status (favourited has correct semantics)
        if summary_data.get("is_favorited"):
            try:
                await client.update_bookmark(
                    bookmark.id,
                    favourited=True,
                )
            except Exception as e:
                logger.warning(
                    "karakeep_update_favourite_failed",
                    extra={"bookmark_id": bookmark.id, "error": str(e)},
                )

        # Add topic tags from summary
        if json_payload:
            topic_tags = json_payload.get("topic_tags", [])
            if len(topic_tags) > 5:
                logger.debug(
                    "karakeep_truncating_tags",
                    extra={"count": len(topic_tags), "limit": 5},
                )
            # Clean hashtags and add
            for tag in topic_tags[:5]:  # Limit to 5 topic tags
                clean_tag = tag.lstrip("#").strip()
                if clean_tag:
                    tags.append(clean_tag)

        # Attach tags
        if tags:
            try:
                await client.attach_tags(bookmark.id, tags)
            except Exception as e:
                # Tag attachment failed - cleanup by deleting the bookmark
                logger.warning(
                    "karakeep_attach_tags_failed_cleanup",
                    extra={"bookmark_id": bookmark.id, "error": str(e)},
                )
                try:
                    await client.delete_bookmark(bookmark.id)
                except Exception as cleanup_err:
                    logger.error(
                        "karakeep_cleanup_delete_failed",
                        extra={"bookmark_id": bookmark.id, "error": str(cleanup_err)},
                    )
                raise  # Re-raise the original tag attachment error

        # Mark as synced
        sync_id = await self._repository.async_create_sync_record(
            bsr_summary_id=summary_id,
            karakeep_bookmark_id=bookmark.id,
            url_hash=_url_hash(url),
            sync_direction="bsr_to_karakeep",
            synced_at=datetime.now(UTC),
            bsr_modified_at=summary_data.get("updated_at"),
        )

        if sync_id is None:
            # Duplicate sync record - another sync beat us to it
            # Delete the bookmark we just created to avoid orphans
            logger.warning(
                "karakeep_sync_record_duplicate_cleanup",
                extra={"bookmark_id": bookmark.id, "summary_id": summary_id},
            )
            try:
                await client.delete_bookmark(bookmark.id)
            except Exception as cleanup_err:
                logger.error(
                    "karakeep_duplicate_cleanup_failed",
                    extra={"bookmark_id": bookmark.id, "error": str(cleanup_err)},
                )
            raise RuntimeError("Duplicate sync record detected")

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
        if not self._repository:
            raise RuntimeError("Repository not configured for sync service")

        start_time = time.time()
        result = SyncResult(direction="karakeep_to_bsr")

        try:
            async with KarakeepClient(self.api_url, self.api_key) as client:
                # Health check before proceeding
                if not await client.health_check():
                    result.errors.append("Karakeep API health check failed")
                    logger.error("karakeep_sync_health_check_failed")
                    return result

                # Build normalized URL index (batched for memory efficiency)
                karakeep_url_index = await self._build_karakeep_url_index(client)

                # Get already synced hashes
                synced_hashes = await self._repository.async_get_synced_hashes_by_direction(
                    "karakeep_to_bsr"
                )

                # Get existing BSR URLs (via dedupe_hash)
                existing_hashes = await self._repository.async_get_existing_request_hashes()

                items_to_sync: list[KarakeepBookmark] = []
                for normalized_url, bookmark in karakeep_url_index.items():
                    if not bookmark.url:
                        continue
                    url_hash = _url_hash(bookmark.url)

                    # Skip if already synced from Karakeep (handles legacy hash format)
                    if _check_hash_in_set(url_hash, synced_hashes):
                        result.items_skipped += 1
                        continue

                    # Check if already exists in BSR using full hash
                    dedupe = url_hash_sha256(normalized_url)
                    if dedupe in existing_hashes:
                        # Mark as synced since it exists
                        await self._repository.async_create_sync_record(
                            karakeep_bookmark_id=bookmark.id,
                            url_hash=url_hash,
                            sync_direction="karakeep_to_bsr",
                            synced_at=datetime.now(UTC),
                        )
                        result.items_skipped += 1
                        continue

                    items_to_sync.append(bookmark)
                    if limit and len(items_to_sync) >= limit:
                        break

                # Submit URLs to BSR for processing
                for bookmark in items_to_sync:
                    try:
                        await self._submit_url_to_bsr(bookmark, user_id)
                        result.items_synced += 1
                    except Exception as e:
                        result.items_failed += 1
                        result.errors.append(f"Failed to sync bookmark {bookmark.id}: {e}")
                        logger.warning(
                            "karakeep_sync_bookmark_failed",
                            extra={"bookmark_id": bookmark.id, "error": str(e)},
                        )

        except KarakeepClientError as e:
            result.errors.append(f"Karakeep client error: {e}")
            logger.error("karakeep_sync_client_error", extra={"error": str(e)})
        except Exception as e:
            result.errors.append(f"Unexpected error: {e}")
            logger.exception("karakeep_sync_unexpected_error")

        result.duration_seconds = time.time() - start_time
        logger.info(
            "karakeep_sync_karakeep_to_bsr_complete",
            extra={
                "synced": result.items_synced,
                "skipped": result.items_skipped,
                "failed": result.items_failed,
                "duration": result.duration_seconds,
            },
        )
        return result

    async def _submit_url_to_bsr(self, bookmark: KarakeepBookmark, user_id: int) -> None:
        """Submit a Karakeep bookmark URL to BSR for processing.

        Args:
            bookmark: Karakeep bookmark
            user_id: BSR user ID
        """
        if not self._repository:
            raise RuntimeError("Repository not configured for sync service")

        url = bookmark.url
        if not url:
            return

        normalized = normalize_url(url)
        dedupe_hash = url_hash_sha256(normalized) if normalized else None

        # Create BSR request
        await self._repository.async_create_request_from_karakeep(
            user_id=user_id,
            input_url=url,
            normalized_url=normalized,
            dedupe_hash=dedupe_hash,
        )

        # Mark as synced
        sync_id = await self._repository.async_create_sync_record(
            bsr_summary_id=None,  # Will be set when summary is created
            karakeep_bookmark_id=bookmark.id,
            url_hash=_url_hash(url),
            sync_direction="karakeep_to_bsr",
            synced_at=datetime.now(UTC),
        )

        if sync_id is None:
            # Duplicate - another sync beat us to it
            logger.warning(
                "karakeep_submit_url_duplicate",
                extra={"bookmark_id": bookmark.id, "url": url},
            )
            raise RuntimeError("Duplicate sync record detected")

        logger.info(
            "karakeep_url_submitted_to_bsr",
            extra={
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
        if not self._repository:
            raise RuntimeError("Repository not configured for sync service")

        return await self._repository.async_get_sync_stats()

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
        if not self._repository:
            raise RuntimeError("Repository not configured for sync service")

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

        try:
            async with KarakeepClient(self.api_url, self.api_key) as client:
                # Health check
                if not await client.health_check():
                    preview["errors"].append("Karakeep API health check failed")
                    return preview

                # Build normalized URL index (batched for memory efficiency)
                karakeep_url_index = await self._build_karakeep_url_index(client)

                # Get already synced hashes
                synced_hashes_bsr = await self._repository.async_get_synced_hashes_by_direction(
                    "bsr_to_karakeep"
                )
                synced_hashes_kk = await self._repository.async_get_synced_hashes_by_direction(
                    "karakeep_to_bsr"
                )

                # BSR -> Karakeep preview
                summaries_data = await self._repository.async_get_summaries_for_sync(
                    user_id=user_id
                )

                count = 0
                for summary_data in summaries_data:
                    if limit and count >= limit:
                        break
                    request_data = summary_data.get("request_data", {})
                    url = request_data.get("normalized_url")
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
                existing_hashes = await self._repository.async_get_existing_request_hashes()

                count = 0
                for normalized_url, bookmark in karakeep_url_index.items():
                    if limit and count >= limit:
                        break
                    if not bookmark.url:
                        continue
                    url_hash = _url_hash(bookmark.url)

                    # Check if already synced (handles legacy hash format)
                    if _check_hash_in_set(url_hash, synced_hashes_kk):
                        preview["karakeep_to_bsr"]["would_skip"] += 1
                        continue

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
                        continue

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
            Dict with update counts
        """
        if not self._repository:
            raise RuntimeError("Repository not configured for sync service")

        bsr_to_kk_updated = 0
        kk_to_bsr_updated = 0
        errors: list[str] = []

        try:
            async with KarakeepClient(self.api_url, self.api_key) as client:
                # Health check
                if not await client.health_check():
                    errors.append("Karakeep API health check failed")
                    logger.error("karakeep_status_sync_health_check_failed")
                    return {
                        "bsr_to_karakeep_updated": 0,
                        "karakeep_to_bsr_updated": 0,
                        "errors": errors,
                    }

                # Get all Karakeep bookmarks for status lookup
                karakeep_bookmarks = await client.get_all_bookmarks()
                karakeep_by_id = {b.id: b for b in karakeep_bookmarks}

                # Get all synced items that have Karakeep bookmark IDs and summary IDs
                synced_items = (
                    await self._repository.async_get_synced_items_with_bookmark_and_summary()
                )

                for sync_record in synced_items:
                    try:
                        summary_id = sync_record.get("bsr_summary")
                        bookmark_id = sync_record.get("karakeep_bookmark_id")
                        sync_id = sync_record.get("id")

                        if not summary_id or not bookmark_id or not sync_id:
                            continue

                        # Get BSR summary
                        summary_data = await self._repository.async_get_summary_by_id(summary_id)
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

                        # Use timestamps for conflict resolution if both timestamps exist
                        bsr_modified_at = sync_record.get("bsr_modified_at")
                        karakeep_modified_at = sync_record.get("karakeep_modified_at")
                        if bsr_modified_at and karakeep_modified_at:
                            # Check which was modified more recently
                            summary_updated_at = summary_data.get("updated_at")
                            if summary_updated_at and summary_updated_at > bsr_modified_at:
                                # BSR was updated after last sync
                                bsr_is_source = True
                            # Note: We can't easily detect Karakeep modifications
                            # without storing bookmark modification timestamps

                        if bsr_is_source:
                            # Sync BSR -> Karakeep
                            needs_update = False
                            tags_to_add: list[str] = []
                            tags_to_remove: list[str] = []

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
                                await client.update_bookmark(
                                    bookmark.id,
                                    favourited=bsr_fav,
                                )
                                needs_update = True

                            # Apply tag changes
                            if tags_to_add:
                                await client.attach_tags(bookmark.id, tags_to_add)
                            for tag_id in tags_to_remove:
                                await client.detach_tag(bookmark.id, tag_id)

                            if needs_update:
                                # Update sync record timestamps
                                await self._repository.async_update_sync_timestamps(
                                    sync_id,
                                    bsr_modified_at=summary_data.get("updated_at"),
                                    karakeep_modified_at=datetime.now(UTC),
                                )
                                bsr_to_kk_updated += 1
                                logger.debug(
                                    "karakeep_status_synced_to_karakeep",
                                    extra={
                                        "bookmark_id": bookmark.id,
                                        "read_tag": bsr_read,
                                        "favourited": bsr_fav,
                                    },
                                )

                        # Sync Karakeep -> BSR
                        elif kk_has_read_tag != bsr_read or kk_fav != bsr_fav:
                            await self._repository.async_update_summary_status(
                                summary_id,
                                is_read=kk_has_read_tag,
                                is_favorited=kk_fav,
                            )

                            # Update sync record timestamps
                            await self._repository.async_update_sync_timestamps(
                                sync_id,
                                bsr_modified_at=datetime.now(UTC),
                                karakeep_modified_at=datetime.now(UTC),
                            )

                            kk_to_bsr_updated += 1
                            logger.debug(
                                "karakeep_status_synced_to_bsr",
                                extra={
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
                            extra={"sync_id": sync_record.get("id"), "error": str(e)},
                        )

        except Exception as e:
            errors.append(f"Status sync failed: {e}")
            logger.exception("karakeep_status_sync_failed")

        logger.info(
            "karakeep_status_sync_complete",
            extra={
                "bsr_to_karakeep": bsr_to_kk_updated,
                "karakeep_to_bsr": kk_to_bsr_updated,
                "errors": len(errors),
            },
        )

        return {
            "bsr_to_karakeep_updated": bsr_to_kk_updated,
            "karakeep_to_bsr_updated": kk_to_bsr_updated,
            "errors": errors,
        }
