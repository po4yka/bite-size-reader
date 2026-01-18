"""SQLite implementation of Karakeep sync repository.

This adapter handles KarakeepSync model operations asynchronously.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import peewee

from app.core.time_utils import UTC
from app.db.models import KarakeepSync, Request, Summary, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteKarakeepSyncRepositoryAdapter(SqliteBaseRepository):
    """Adapter for KarakeepSync database operations.

    Replaces direct synchronous Peewee calls with async repository pattern.
    """

    async def async_get_synced_hashes_by_direction(self, sync_direction: str) -> set[str]:
        """Get all URL hashes synced in a given direction.

        Args:
            sync_direction: Either 'bsr_to_karakeep' or 'karakeep_to_bsr'

        Returns:
            Set of URL hashes
        """

        def _query() -> set[str]:
            return {
                s.url_hash
                for s in KarakeepSync.select(KarakeepSync.url_hash).where(
                    KarakeepSync.sync_direction == sync_direction
                )
            }

        return await self._execute(_query, operation_name="get_synced_hashes", read_only=True)

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
    ) -> int | None:
        """Create a sync record.

        Args:
            bsr_summary_id: BSR summary ID (optional)
            karakeep_bookmark_id: Karakeep bookmark ID
            url_hash: URL hash for deduplication
            sync_direction: Sync direction
            synced_at: When the sync occurred
            bsr_modified_at: Last BSR modification time
            karakeep_modified_at: Last Karakeep modification time

        Returns:
            Created record ID, or None if duplicate
        """

        def _create() -> int | None:
            try:
                record = KarakeepSync.create(
                    bsr_summary=bsr_summary_id,
                    karakeep_bookmark_id=karakeep_bookmark_id,
                    url_hash=url_hash,
                    sync_direction=sync_direction,
                    synced_at=synced_at or datetime.now(UTC),
                    bsr_modified_at=bsr_modified_at,
                    karakeep_modified_at=karakeep_modified_at,
                )
                return record.id
            except peewee.IntegrityError:
                # Duplicate record - return None to signal already exists
                return None

        return await self._execute(_create, operation_name="create_sync_record")

    async def async_get_synced_items_with_bookmark_and_summary(
        self,
    ) -> list[dict[str, Any]]:
        """Get all synced items that have both bookmark ID and summary ID.

        Returns:
            List of sync records with their summary data
        """

        def _query() -> list[dict[str, Any]]:
            records = KarakeepSync.select().where(
                KarakeepSync.karakeep_bookmark_id.is_null(False),
                KarakeepSync.bsr_summary.is_null(False),
            )
            results: list[dict[str, Any]] = []
            for r in records:
                data = model_to_dict(r)
                if data is not None:
                    results.append(data)
            return results

        return await self._execute(_query, operation_name="get_synced_items", read_only=True)

    async def async_update_sync_timestamps(
        self,
        sync_id: int,
        bsr_modified_at: datetime | None = None,
        karakeep_modified_at: datetime | None = None,
    ) -> None:
        """Update timestamp fields on a sync record.

        Args:
            sync_id: Sync record ID
            bsr_modified_at: New BSR modification time
            karakeep_modified_at: New Karakeep modification time
        """

        def _update() -> None:
            update_data: dict[Any, Any] = {}
            if bsr_modified_at is not None:
                update_data[KarakeepSync.bsr_modified_at] = bsr_modified_at
            if karakeep_modified_at is not None:
                update_data[KarakeepSync.karakeep_modified_at] = karakeep_modified_at
            if update_data:
                KarakeepSync.update(update_data).where(KarakeepSync.id == sync_id).execute()

        await self._execute(_update, operation_name="update_sync_timestamps")

    async def async_get_sync_stats(self) -> dict[str, Any]:
        """Get sync statistics.

        Returns:
            Dict with total_synced, bsr_to_karakeep count, karakeep_to_bsr count,
            and last_sync_at timestamp
        """

        def _query() -> dict[str, Any]:
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
                "last_sync_at": (last_sync.synced_at.isoformat() if last_sync else None),
            }

        return await self._execute(_query, operation_name="get_sync_stats", read_only=True)

    async def async_get_summaries_for_sync(
        self,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get summaries eligible for sync to Karakeep.

        Args:
            user_id: Optional user ID filter

        Returns:
            List of summary dicts with request data
        """

        def _query() -> list[dict[str, Any]]:
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

            results = []
            for summary in query:
                data = model_to_dict(summary)
                if data:
                    data["request_data"] = model_to_dict(summary.request)
                    results.append(data)
            return results

        return await self._execute(_query, operation_name="get_summaries_for_sync", read_only=True)

    async def async_get_existing_request_hashes(self) -> set[str]:
        """Get all existing request dedupe hashes.

        Returns:
            Set of dedupe hashes from requests table
        """

        def _query() -> set[str]:
            return {
                r.dedupe_hash
                for r in Request.select(Request.dedupe_hash).where(
                    Request.dedupe_hash.is_null(False)
                )
            }

        return await self._execute(_query, operation_name="get_existing_hashes", read_only=True)

    async def async_create_request_from_karakeep(
        self,
        *,
        user_id: int,
        input_url: str,
        normalized_url: str | None,
        dedupe_hash: str | None,
    ) -> int:
        """Create a new request record from a Karakeep bookmark.

        Args:
            user_id: User ID to associate
            input_url: Original URL
            normalized_url: Normalized URL
            dedupe_hash: Deduplication hash

        Returns:
            Created request ID
        """

        def _create() -> int:
            request = Request.create(
                type="url",
                status="pending",
                user_id=user_id,
                input_url=input_url,
                normalized_url=normalized_url,
                dedupe_hash=dedupe_hash,
            )
            return request.id

        return await self._execute(_create, operation_name="create_request_from_karakeep")

    async def async_get_summary_by_id(self, summary_id: int) -> dict[str, Any] | None:
        """Get a summary by ID with its request.

        Args:
            summary_id: Summary ID

        Returns:
            Summary dict with request data, or None
        """

        def _get() -> dict[str, Any] | None:
            summary = Summary.get_or_none(Summary.id == summary_id)
            if not summary:
                return None
            data = model_to_dict(summary)
            if data:
                data["request_data"] = model_to_dict(summary.request)
            return data

        return await self._execute(_get, operation_name="get_summary_by_id", read_only=True)

    async def async_update_summary_status(
        self,
        summary_id: int,
        is_read: bool | None = None,
        is_favorited: bool | None = None,
    ) -> None:
        """Update summary read/favorite status.

        Args:
            summary_id: Summary ID
            is_read: New read status (optional)
            is_favorited: New favorited status (optional)
        """

        def _update() -> None:
            update_data: dict[Any, Any] = {}
            if is_read is not None:
                update_data[Summary.is_read] = is_read
            if is_favorited is not None:
                update_data[Summary.is_favorited] = is_favorited
            if update_data:
                Summary.update(update_data).where(Summary.id == summary_id).execute()

        await self._execute(_update, operation_name="update_summary_status")

    async def async_get_crawl_result_title(self, request_id: int) -> str | None:
        """Get the title from a crawl result's metadata.

        Args:
            request_id: Request ID to look up

        Returns:
            Title string or None
        """
        from app.db.models import CrawlResult

        def _get() -> str | None:
            crawl = CrawlResult.get_or_none(CrawlResult.request == request_id)
            if crawl and crawl.metadata_json:
                return crawl.metadata_json.get("title")
            return None

        return await self._execute(_get, operation_name="get_crawl_result_title", read_only=True)
