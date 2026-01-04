"""Karakeep sync service for bidirectional synchronization."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING

from app.adapters.karakeep.client import KarakeepClient, KarakeepClientError
from app.adapters.karakeep.models import FullSyncResult, SyncResult
from app.core.url_utils import normalize_url

if TYPE_CHECKING:
    from app.db.models import Summary

logger = logging.getLogger(__name__)


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
                            # Already in Karakeep, mark as synced
                            KarakeepSync.create(
                                bsr_summary_id=summary.id,
                                url_hash=url_hash,
                                sync_direction="bsr_to_karakeep",
                                synced_at=datetime.utcnow(),
                            )
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
        except Exception:
            pass

        # Get summary text for note
        if summary.json_payload:
            tldr = summary.json_payload.get("tldr")
            summary_250 = summary.json_payload.get("summary_250")
            note = tldr or summary_250

        # Create bookmark
        bookmark = await client.create_bookmark(url=url, title=title, note=note)

        # Attach tags
        tags = [self.sync_tag]
        if summary.json_payload:
            topic_tags = summary.json_payload.get("topic_tags", [])
            # Clean hashtags
            for tag in topic_tags[:5]:  # Limit to 5 tags
                clean_tag = tag.lstrip("#").strip()
                if clean_tag:
                    tags.append(clean_tag)

        if tags:
            try:
                await client.attach_tags(bookmark.id, tags)
            except Exception as e:
                logger.warning(
                    "karakeep_attach_tags_failed",
                    extra={"bookmark_id": bookmark.id, "error": str(e)},
                )

        # Mark as synced
        KarakeepSync.create(
            bsr_summary_id=summary.id,
            karakeep_bookmark_id=bookmark.id,
            url_hash=_url_hash(url),
            sync_direction="bsr_to_karakeep",
            synced_at=datetime.utcnow(),
        )

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
                            # Mark as synced since it exists
                            KarakeepSync.create(
                                karakeep_bookmark_id=bookmark.id,
                                url_hash=url_hash,
                                sync_direction="karakeep_to_bsr",
                                synced_at=datetime.utcnow(),
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

        # Mark as synced
        KarakeepSync.create(
            bsr_summary_id=None,  # Will be set when summary is created
            karakeep_bookmark_id=bookmark.id,  # type: ignore[attr-defined]
            url_hash=_url_hash(url),
            sync_direction="karakeep_to_bsr",
            synced_at=datetime.utcnow(),
        )

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
