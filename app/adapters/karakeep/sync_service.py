"""Karakeep sync service for bidirectional synchronization."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import peewee

from app.adapters.karakeep.client import KarakeepClient, KarakeepClientError
from app.adapters.karakeep.models import FullSyncResult, SyncResult
from app.core.url_utils import normalize_url

if TYPE_CHECKING:
    from app.db.models import Summary

logger = logging.getLogger(__name__)

# Tag names for status tracking (instead of using archived field)
TAG_BSR_READ = "bsr-read"
TAG_BSR_SYNCED = "bsr-synced"


def _url_hash(url: str) -> str:
    """Generate consistent hash for URL deduplication."""
    normalized = normalize_url(url) or url
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


class KarakeepSyncService:
    """Bidirectional sync service between BSR and Karakeep."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        sync_tag: str = "bsr-synced",
    ) -> None:
        """Initialize sync service.

        Args:
            api_url: Karakeep API URL
            api_key: Karakeep API key
            sync_tag: Tag to mark synced items
        """
        self.api_url = api_url
        self.api_key = api_key
        self.sync_tag = sync_tag

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
        from app.db.models import KarakeepSync, Request, Summary, database_proxy

        start_time = time.time()
        result = SyncResult(direction="bsr_to_karakeep")

        try:
            async with KarakeepClient(self.api_url, self.api_key) as client:
                # Health check before proceeding
                if not await client.health_check():
                    result.errors.append("Karakeep API health check failed")
                    logger.error("karakeep_sync_health_check_failed")
                    return result

                # Get existing Karakeep bookmarks for deduplication
                karakeep_bookmarks = await client.get_all_bookmarks()
                karakeep_urls = {b.url for b in karakeep_bookmarks if b.url}

                # Query BSR summaries not yet synced
                with database_proxy.atomic():
                    query = (
                        Summary.select(Summary, Request)
                        .join(Request)
                        .where(
                            Summary.is_deleted == False,  # noqa: E712
                            Request.normalized_url.is_null(False),
                        )
                    )

                    if user_id:
                        query = query.where(Request.user_id == user_id)

                    # Exclude already synced
                    synced_hashes = {
                        s.url_hash
                        for s in KarakeepSync.select(KarakeepSync.url_hash).where(
                            KarakeepSync.sync_direction == "bsr_to_karakeep"
                        )
                    }

                    summaries_to_sync: list[Summary] = []
                    for summary in query:
                        url = summary.request.normalized_url
                        if not url:
                            continue
                        url_hash = _url_hash(url)

                        # Skip if already synced or exists in Karakeep
                        if url_hash in synced_hashes:
                            result.items_skipped += 1
                            continue
                        if url in karakeep_urls:
                            # Already in Karakeep, mark as synced (with unique constraint handling)
                            try:
                                KarakeepSync.create(
                                    bsr_summary=summary,
                                    url_hash=url_hash,
                                    sync_direction="bsr_to_karakeep",
                                    synced_at=datetime.now(timezone.utc),
                                    bsr_modified_at=summary.updated_at,
                                )
                            except peewee.IntegrityError:
                                # Record already exists (race condition), skip
                                pass
                            result.items_skipped += 1
                            continue

                        summaries_to_sync.append(summary)
                        if limit and len(summaries_to_sync) >= limit:
                            break

                # Sync each summary to Karakeep
                for summary in summaries_to_sync:
                    try:
                        await self._sync_summary_to_karakeep(client, summary)
                        result.items_synced += 1
                    except Exception as e:
                        result.items_failed += 1
                        result.errors.append(f"Failed to sync summary {summary.id}: {e}")
                        logger.warning(
                            "karakeep_sync_item_failed",
                            extra={"summary_id": summary.id, "error": str(e)},
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
        summary: Summary,
    ) -> None:
        """Sync a single BSR summary to Karakeep.

        Args:
            client: Karakeep client
            summary: BSR summary to sync

        Raises:
            Exception: If sync fails after cleanup attempt
        """
        from app.db.models import CrawlResult, KarakeepSync

        url = summary.request.normalized_url
        if not url:
            return

        # Get metadata
        title = None
        note = None

        # Try to get title from crawl result
        try:
            crawl = CrawlResult.get_or_none(CrawlResult.request == summary.request)
            if crawl and crawl.metadata_json:
                title = crawl.metadata_json.get("title")
        except Exception as e:
            logger.warning(
                "karakeep_crawl_result_fetch_failed",
                extra={"request_id": summary.request.id, "error": str(e)},
            )

        # Get summary text for note
        if summary.json_payload:
            tldr = summary.json_payload.get("tldr")
            summary_250 = summary.json_payload.get("summary_250")
            note = tldr or summary_250

        # Create bookmark
        bookmark = await client.create_bookmark(url=url, title=title, note=note)

        # Build tags list
        tags = [TAG_BSR_SYNCED]

        # Use 'bsr-read' tag for read status instead of archived field
        if summary.is_read:
            tags.append(TAG_BSR_READ)

        # Sync favorite status (favourited has correct semantics)
        if summary.is_favorited:
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
        if summary.json_payload:
            topic_tags = summary.json_payload.get("topic_tags", [])
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

        # Mark as synced (with unique constraint handling)
        try:
            KarakeepSync.create(
                bsr_summary=summary,
                karakeep_bookmark_id=bookmark.id,
                url_hash=_url_hash(url),
                sync_direction="bsr_to_karakeep",
                synced_at=datetime.now(timezone.utc),
                bsr_modified_at=summary.updated_at,
            )
        except peewee.IntegrityError:
            # Duplicate sync record - another sync beat us to it
            # Delete the bookmark we just created to avoid orphans
            logger.warning(
                "karakeep_sync_record_duplicate_cleanup",
                extra={"bookmark_id": bookmark.id, "summary_id": summary.id},
            )
            try:
                await client.delete_bookmark(bookmark.id)
            except Exception as cleanup_err:
                logger.error(
                    "karakeep_duplicate_cleanup_failed",
                    extra={"bookmark_id": bookmark.id, "error": str(cleanup_err)},
                )
            raise

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
        from app.db.models import KarakeepSync, Request, database_proxy

        start_time = time.time()
        result = SyncResult(direction="karakeep_to_bsr")

        try:
            async with KarakeepClient(self.api_url, self.api_key) as client:
                # Health check before proceeding
                if not await client.health_check():
                    result.errors.append("Karakeep API health check failed")
                    logger.error("karakeep_sync_health_check_failed")
                    return result

                # Get all Karakeep bookmarks
                bookmarks = await client.get_all_bookmarks()

                # Get already synced hashes
                with database_proxy.atomic():
                    synced_hashes = {
                        s.url_hash
                        for s in KarakeepSync.select(KarakeepSync.url_hash).where(
                            KarakeepSync.sync_direction == "karakeep_to_bsr"
                        )
                    }

                    # Get existing BSR URLs (via dedupe_hash)
                    existing_hashes = {
                        r.dedupe_hash
                        for r in Request.select(Request.dedupe_hash).where(
                            Request.dedupe_hash.is_null(False)
                        )
                    }

                items_to_sync = []
                for bookmark in bookmarks:
                    if not bookmark.url:
                        continue

                    url_hash = _url_hash(bookmark.url)

                    # Skip if already synced from Karakeep
                    if url_hash in synced_hashes:
                        result.items_skipped += 1
                        continue

                    # Check if already exists in BSR
                    normalized = normalize_url(bookmark.url)
                    if normalized:
                        dedupe = hashlib.sha256(normalized.encode()).hexdigest()
                        if dedupe in existing_hashes:
                            # Mark as synced since it exists (with unique constraint handling)
                            try:
                                KarakeepSync.create(
                                    karakeep_bookmark_id=bookmark.id,
                                    url_hash=url_hash,
                                    sync_direction="karakeep_to_bsr",
                                    synced_at=datetime.now(timezone.utc),
                                )
                            except peewee.IntegrityError:
                                # Record already exists
                                pass
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

    async def _submit_url_to_bsr(self, bookmark: object, user_id: int) -> None:
        """Submit a Karakeep bookmark URL to BSR for processing.

        Args:
            bookmark: Karakeep bookmark
            user_id: BSR user ID
        """
        from app.db.models import KarakeepSync, Request

        url = bookmark.url  # type: ignore[attr-defined]
        if not url:
            return

        normalized = normalize_url(url)
        dedupe_hash = hashlib.sha256(normalized.encode()).hexdigest() if normalized else None

        # Create BSR request
        request = Request.create(
            type="url",
            status="pending",
            user_id=user_id,
            input_url=url,
            normalized_url=normalized,
            dedupe_hash=dedupe_hash,
        )

        # Mark as synced (with unique constraint handling)
        try:
            KarakeepSync.create(
                bsr_summary=None,  # Will be set when summary is created
                karakeep_bookmark_id=bookmark.id,  # type: ignore[attr-defined]
                url_hash=_url_hash(url),
                sync_direction="karakeep_to_bsr",
                synced_at=datetime.now(timezone.utc),
            )
        except peewee.IntegrityError:
            # Duplicate - another sync beat us to it
            logger.warning(
                "karakeep_submit_url_duplicate",
                extra={"bookmark_id": bookmark.id, "url": url},  # type: ignore[attr-defined]
            )
            raise

        logger.info(
            "karakeep_url_submitted_to_bsr",
            extra={
                "bookmark_id": bookmark.id,  # type: ignore[attr-defined]
                "request_id": request.id,
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
            user_id: User ID for Karakeep→BSR sync (required)
            limit: Maximum items per direction

        Returns:
            Full sync result
        """
        start_time = time.time()

        # BSR → Karakeep
        bsr_result = await self.sync_bsr_to_karakeep(user_id=user_id, limit=limit)

        # Karakeep → BSR (requires user_id)
        if user_id:
            karakeep_result = await self.sync_karakeep_to_bsr(user_id=user_id, limit=limit)
        else:
            karakeep_result = SyncResult(direction="karakeep_to_bsr")
            karakeep_result.errors.append("Skipped: user_id required for Karakeep→BSR sync")

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

    async def get_sync_status(self) -> dict:
        """Get current sync status and stats.

        Returns:
            Dict with sync statistics
        """
        from app.db.models import KarakeepSync, database_proxy

        with database_proxy.atomic():
            total_synced = KarakeepSync.select().count()
            bsr_to_karakeep = (
                KarakeepSync.select()
                .where(KarakeepSync.sync_direction == "bsr_to_karakeep")
                .count()
            )
            karakeep_to_bsr = (
                KarakeepSync.select()
                .where(KarakeepSync.sync_direction == "karakeep_to_bsr")
                .count()
            )

            last_sync = (
                KarakeepSync.select().order_by(KarakeepSync.synced_at.desc()).limit(1).first()
            )

        return {
            "total_synced": total_synced,
            "bsr_to_karakeep": bsr_to_karakeep,
            "karakeep_to_bsr": karakeep_to_bsr,
            "last_sync_at": last_sync.synced_at.isoformat() if last_sync else None,
        }

    async def preview_sync(
        self,
        user_id: int | None = None,
        limit: int | None = None,
    ) -> dict:
        """Preview what would be synced without making changes (dry-run).

        Args:
            user_id: Optional user ID filter
            limit: Maximum items to preview per direction

        Returns:
            Dict with preview information
        """
        from app.db.models import KarakeepSync, Request, Summary, database_proxy

        preview: dict = {
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

                # Get existing Karakeep bookmarks
                karakeep_bookmarks = await client.get_all_bookmarks()
                karakeep_urls = {b.url for b in karakeep_bookmarks if b.url}
                karakeep_url_to_bookmark = {b.url: b for b in karakeep_bookmarks if b.url}

                # Get already synced hashes
                with database_proxy.atomic():
                    synced_hashes_bsr = {
                        s.url_hash
                        for s in KarakeepSync.select(KarakeepSync.url_hash).where(
                            KarakeepSync.sync_direction == "bsr_to_karakeep"
                        )
                    }
                    synced_hashes_kk = {
                        s.url_hash
                        for s in KarakeepSync.select(KarakeepSync.url_hash).where(
                            KarakeepSync.sync_direction == "karakeep_to_bsr"
                        )
                    }

                    # BSR → Karakeep preview
                    query = (
                        Summary.select(Summary, Request)
                        .join(Request)
                        .where(
                            Summary.is_deleted == False,  # noqa: E712
                            Request.normalized_url.is_null(False),
                        )
                    )
                    if user_id:
                        query = query.where(Request.user_id == user_id)

                    count = 0
                    for summary in query:
                        if limit and count >= limit:
                            break
                        url = summary.request.normalized_url
                        if not url:
                            continue
                        url_hash = _url_hash(url)

                        if url_hash in synced_hashes_bsr:
                            preview["bsr_to_karakeep"]["would_skip"] += 1
                            continue
                        if url in karakeep_urls:
                            preview["bsr_to_karakeep"]["already_exists_in_karakeep"].append({
                                "summary_id": summary.id,
                                "url": url,
                                "karakeep_id": karakeep_url_to_bookmark[url].id,
                            })
                            preview["bsr_to_karakeep"]["would_skip"] += 1
                            continue

                        # Would be synced
                        title = None
                        if summary.json_payload:
                            title = summary.json_payload.get("summary_250", "")[:100]
                        preview["bsr_to_karakeep"]["would_sync"].append({
                            "summary_id": summary.id,
                            "url": url,
                            "title": title,
                            "is_read": summary.is_read,
                            "is_favorited": summary.is_favorited,
                        })
                        count += 1

                    # Karakeep → BSR preview
                    existing_hashes = {
                        r.dedupe_hash
                        for r in Request.select(Request.dedupe_hash).where(
                            Request.dedupe_hash.is_null(False)
                        )
                    }

                    count = 0
                    for bookmark in karakeep_bookmarks:
                        if limit and count >= limit:
                            break
                        if not bookmark.url:
                            continue
                        url_hash = _url_hash(bookmark.url)

                        if url_hash in synced_hashes_kk:
                            preview["karakeep_to_bsr"]["would_skip"] += 1
                            continue

                        normalized = normalize_url(bookmark.url)
                        if normalized:
                            dedupe = hashlib.sha256(normalized.encode()).hexdigest()
                            if dedupe in existing_hashes:
                                preview["karakeep_to_bsr"]["already_exists_in_bsr"].append({
                                    "karakeep_id": bookmark.id,
                                    "url": bookmark.url,
                                })
                                preview["karakeep_to_bsr"]["would_skip"] += 1
                                continue

                        # Would be synced
                        preview["karakeep_to_bsr"]["would_sync"].append({
                            "karakeep_id": bookmark.id,
                            "url": bookmark.url,
                            "title": bookmark.title,
                            "archived": bookmark.archived,
                            "favourited": bookmark.favourited,
                        })
                        count += 1

        except KarakeepClientError as e:
            preview["errors"].append(f"Karakeep client error: {e}")
        except Exception as e:
            preview["errors"].append(f"Unexpected error: {e}")

        return preview

    async def sync_status_updates(self) -> dict[str, int | list[str]]:
        """Sync read/favorite status for already-synced items.

        This updates:
        - BSR is_read → Karakeep 'bsr-read' tag
        - BSR is_favorited → Karakeep favourited
        - Karakeep 'bsr-read' tag → BSR is_read
        - Karakeep favourited → BSR is_favorited

        Uses timestamp-based conflict resolution when both have been modified.

        Returns:
            Dict with update counts
        """
        from app.db.models import KarakeepSync, Summary, database_proxy

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

                with database_proxy.atomic():
                    # Get all synced items that have Karakeep bookmark IDs
                    synced_items = KarakeepSync.select().where(
                        KarakeepSync.karakeep_bookmark_id.is_null(False),
                        KarakeepSync.bsr_summary_id.is_null(False),
                    )

                    for sync_record in synced_items:
                        try:
                            # Get BSR summary
                            summary = Summary.get_or_none(Summary.id == sync_record.bsr_summary_id)
                            if not summary:
                                continue

                            # Get Karakeep bookmark
                            bookmark = karakeep_by_id.get(sync_record.karakeep_bookmark_id)
                            if not bookmark:
                                continue

                            # Determine read status from Karakeep tags (not archived field)
                            kk_has_read_tag = any(
                                t.name == TAG_BSR_READ for t in (bookmark.tags or [])
                            )
                            kk_fav = bookmark.favourited

                            bsr_read = summary.is_read
                            bsr_fav = summary.is_favorited

                            # Determine source of truth based on sync direction and timestamps
                            bsr_is_source = sync_record.sync_direction == "bsr_to_karakeep"

                            # Use timestamps for conflict resolution if both timestamps exist
                            if sync_record.bsr_modified_at and sync_record.karakeep_modified_at:
                                # Check which was modified more recently
                                if summary.updated_at > sync_record.bsr_modified_at:
                                    # BSR was updated after last sync
                                    bsr_is_source = True
                                # Note: We can't easily detect Karakeep modifications
                                # without storing bookmark modification timestamps

                            if bsr_is_source:
                                # Sync BSR → Karakeep
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
                                    sync_record.bsr_modified_at = summary.updated_at
                                    sync_record.karakeep_modified_at = datetime.now(timezone.utc)
                                    sync_record.save()
                                    bsr_to_kk_updated += 1
                                    logger.debug(
                                        "karakeep_status_synced_to_karakeep",
                                        extra={
                                            "bookmark_id": bookmark.id,
                                            "read_tag": bsr_read,
                                            "favourited": bsr_fav,
                                        },
                                    )

                            else:
                                # Sync Karakeep → BSR
                                if kk_has_read_tag != bsr_read or kk_fav != bsr_fav:
                                    summary.is_read = kk_has_read_tag
                                    summary.is_favorited = kk_fav
                                    summary.save()

                                    # Update sync record timestamps
                                    sync_record.bsr_modified_at = datetime.now(timezone.utc)
                                    sync_record.karakeep_modified_at = datetime.now(timezone.utc)
                                    sync_record.save()

                                    kk_to_bsr_updated += 1
                                    logger.debug(
                                        "karakeep_status_synced_to_bsr",
                                        extra={
                                            "summary_id": summary.id,
                                            "is_read": kk_has_read_tag,
                                            "is_favorited": kk_fav,
                                        },
                                    )

                        except Exception as e:
                            error_msg = f"Failed to sync status for {sync_record.id}: {e}"
                            errors.append(error_msg)
                            logger.warning(
                                "karakeep_status_sync_item_failed",
                                extra={"sync_id": sync_record.id, "error": str(e)},
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
