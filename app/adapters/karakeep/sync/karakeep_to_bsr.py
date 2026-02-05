"""Karakeep -> BSR sync use-case implementation."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.adapters.karakeep.client import KarakeepClientError
from app.adapters.karakeep.models import SyncResult
from app.adapters.karakeep.sync.errors import record_error
from app.adapters.karakeep.sync.hashing import _check_hash_in_set, _url_hash
from app.core.url_utils import normalize_url, url_hash_sha256
from app.utils.retry_utils import is_transient_error

if TYPE_CHECKING:
    from app.adapters.karakeep.models import KarakeepBookmark
    from app.adapters.karakeep.sync.cache import KarakeepBookmarkCache
    from app.adapters.karakeep.sync.protocols import KarakeepClientProtocol, KarakeepSyncRepository

logger = logging.getLogger(__name__)


class KarakeepToBsrSyncer:
    def __init__(self, *, cache: KarakeepBookmarkCache) -> None:
        self._cache = cache

    async def sync(
        self,
        client: KarakeepClientProtocol,
        repository: KarakeepSyncRepository,
        *,
        user_id: int,
        limit: int | None,
        correlation_id: str,
    ) -> SyncResult:
        start_time = time.time()
        result = SyncResult(direction="karakeep_to_bsr")
        logger.info(
            "karakeep_sync_karakeep_to_bsr_start",
            extra={"correlation_id": correlation_id, "user_id": user_id, "limit": limit},
        )

        try:
            synced_hashes = await repository.async_get_synced_hashes_by_direction("karakeep_to_bsr")
            existing_hashes = await repository.async_get_existing_request_hashes()

            async def process_bookmark(normalized_url: str, bookmark: KarakeepBookmark) -> bool:
                url_hash = _url_hash(bookmark.url or "")

                if _check_hash_in_set(url_hash, synced_hashes):
                    result.skipped_already_synced += 1
                    return False

                dedupe = url_hash_sha256(normalized_url)
                if dedupe in existing_hashes:
                    await repository.async_create_sync_record(
                        karakeep_bookmark_id=bookmark.id,
                        url_hash=url_hash,
                        sync_direction="karakeep_to_bsr",
                        synced_at=datetime.now(UTC),
                        karakeep_modified_at=bookmark.modified_at,
                    )
                    result.skipped_exists_in_target += 1
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
                except Exception as exc:
                    result.items_failed += 1
                    error_message = f"Failed to sync bookmark {bookmark.id}: {exc}"
                    record_error(result, error_message, is_transient_error(exc))
                    logger.warning(
                        "karakeep_sync_bookmark_failed",
                        extra={
                            "correlation_id": correlation_id,
                            "bookmark_id": bookmark.id,
                            "error": str(exc),
                        },
                    )

                return bool(limit and result.items_synced >= limit)

            cached = self._cache.cached_bookmarks()
            if cached is not None:
                for bookmark in cached:
                    if not bookmark.url:
                        continue
                    normalized_url = normalize_url(bookmark.url) or bookmark.url
                    if await process_bookmark(normalized_url, bookmark):
                        break
            else:
                async for normalized_url, bookmark in self._cache.iter_bookmarks(
                    client, correlation_id=correlation_id
                ):
                    if await process_bookmark(normalized_url, bookmark):
                        break

        except KarakeepClientError as exc:
            error_message = f"Karakeep client error: {exc}"
            record_error(result, error_message, is_transient_error(exc))
            logger.error(
                "karakeep_sync_client_error",
                extra={"correlation_id": correlation_id, "error": str(exc)},
            )
        except Exception as exc:
            error_message = f"Unexpected error: {exc}"
            record_error(result, error_message, is_transient_error(exc))
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
        correlation_id: str | None,
    ) -> None:
        url = bookmark.url
        if not url:
            return

        normalized = normalize_url(url)
        dedupe_hash = url_hash_sha256(normalized) if normalized else None

        await repository.async_create_request_from_karakeep(
            user_id=user_id,
            input_url=url,
            normalized_url=normalized,
            dedupe_hash=dedupe_hash,
        )

        sync_id = await repository.async_create_sync_record(
            bsr_summary_id=None,
            karakeep_bookmark_id=bookmark.id,
            url_hash=_url_hash(url),
            sync_direction="karakeep_to_bsr",
            synced_at=datetime.now(UTC),
            karakeep_modified_at=bookmark.modified_at,
        )

        if sync_id is None:
            logger.warning(
                "karakeep_submit_url_duplicate",
                extra={"correlation_id": correlation_id, "bookmark_id": bookmark.id, "url": url},
            )
            raise RuntimeError("Duplicate sync record detected")

        logger.info(
            "karakeep_url_submitted_to_bsr",
            extra={"correlation_id": correlation_id, "bookmark_id": bookmark.id, "url": url},
        )
