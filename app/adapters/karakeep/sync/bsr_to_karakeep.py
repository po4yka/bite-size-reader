"""BSR -> Karakeep sync use-case implementation."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.adapters.karakeep.client import KarakeepClientError
from app.adapters.karakeep.models import SyncResult
from app.adapters.karakeep.sync.errors import record_error
from app.adapters.karakeep.sync.hashing import _check_hash_in_set, _url_hash
from app.adapters.karakeep.sync.metadata import (
    BookmarkMetadataApplier,
    extract_summary_note,
    extract_summary_url,
)
from app.adapters.karakeep.sync.work_items import _SyncWorkItem
from app.core.url_utils import normalize_url
from app.utils.retry_utils import is_transient_error

if TYPE_CHECKING:
    from app.adapters.karakeep.sync.cache import KarakeepBookmarkCache
    from app.adapters.karakeep.sync.protocols import KarakeepClientProtocol, KarakeepSyncRepository
    from app.adapters.karakeep.sync.retry import RetryExecutor

logger = logging.getLogger(__name__)


class BsrToKarakeepSyncer:
    def __init__(
        self,
        *,
        cache: KarakeepBookmarkCache,
        retry: RetryExecutor,
        metadata_applier: BookmarkMetadataApplier,
    ) -> None:
        self._cache = cache
        self._retry = retry
        self._metadata = metadata_applier

    async def sync(
        self,
        client: KarakeepClientProtocol,
        repository: KarakeepSyncRepository,
        *,
        user_id: int | None,
        limit: int | None,
        force: bool,
        correlation_id: str,
    ) -> SyncResult:
        start_time = time.time()
        result = SyncResult(direction="bsr_to_karakeep")
        item_counters: dict[str, int] = {"tags_attached": 0, "favourites_updated": 0}

        logger.info(
            "karakeep_sync_bsr_to_karakeep_start",
            extra={"correlation_id": correlation_id, "user_id": user_id, "limit": limit},
        )

        try:
            karakeep_url_index = await self._cache.get_url_index(
                client, correlation_id=correlation_id
            )

            synced_hashes = await repository.async_get_synced_hashes_by_direction("bsr_to_karakeep")
            summaries_data = await repository.async_get_summaries_for_sync(user_id=user_id)

            work_items: list[_SyncWorkItem] = []
            for summary_data in summaries_data:
                url = extract_summary_url(summary_data)
                if not url:
                    result.skipped_no_url += 1
                    continue
                try:
                    url_hash = _url_hash(url)
                except (ValueError, OSError) as exc:
                    logger.warning(
                        "karakeep_sync_url_hash_failed",
                        extra={
                            "correlation_id": correlation_id,
                            "summary_id": summary_data.get("id"),
                            "url": url[:100],
                            "error": str(exc),
                        },
                    )
                    result.skipped_hash_failed += 1
                    continue

                if not force and _check_hash_in_set(url_hash, synced_hashes):
                    result.skipped_already_synced += 1
                    continue

                try:
                    comparison_url = normalize_url(url) or url
                except (ValueError, OSError):
                    comparison_url = url

                if comparison_url in karakeep_url_index:
                    existing_bookmark = karakeep_url_index[comparison_url]
                    if force:
                        work_items.append(
                            _SyncWorkItem(
                                summary_data=summary_data,
                                url_hash=url_hash,
                                existing_bookmark=existing_bookmark,
                            )
                        )
                    else:
                        await repository.async_create_sync_record(
                            bsr_summary_id=summary_data.get("id"),
                            karakeep_bookmark_id=existing_bookmark.id,
                            url_hash=url_hash,
                            sync_direction="bsr_to_karakeep",
                            synced_at=datetime.now(UTC),
                            bsr_modified_at=summary_data.get("updated_at"),
                            karakeep_modified_at=existing_bookmark.modified_at,
                        )
                        result.skipped_exists_in_target += 1
                        synced_hashes.add(url_hash)
                    continue

                work_items.append(_SyncWorkItem(summary_data=summary_data, url_hash=url_hash))
                if limit and len(work_items) >= limit:
                    break

            for work_item in work_items:
                try:
                    non_fatal_errors = await self._sync_summary_to_karakeep(
                        client,
                        repository,
                        work_item,
                        correlation_id=correlation_id,
                        counters=item_counters,
                    )
                    result.items_synced += 1
                    synced_hashes.add(work_item.url_hash)
                    for message, retryable in non_fatal_errors:
                        record_error(result, message, retryable)
                except Exception as exc:
                    result.items_failed += 1
                    error_message = (
                        f"Failed to sync summary {work_item.summary_data.get('id')}: {exc}"
                    )
                    record_error(result, error_message, is_transient_error(exc))
                    logger.warning(
                        "karakeep_sync_item_failed",
                        extra={
                            "correlation_id": correlation_id,
                            "summary_id": work_item.summary_data.get("id"),
                            "error": str(exc),
                        },
                    )

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
        work_item: _SyncWorkItem,
        *,
        correlation_id: str,
        counters: dict[str, int] | None,
    ) -> list[tuple[str, bool]]:
        summary_data = work_item.summary_data
        non_fatal_errors: list[tuple[str, bool]] = []
        url = extract_summary_url(summary_data)
        if not url:
            return non_fatal_errors

        summary_id = summary_data.get("id")
        request_id = summary_data.get("request_data", {}).get("id")
        existing_bookmark = work_item.existing_bookmark

        title = None
        if request_id:
            try:
                title = await repository.async_get_crawl_result_title(request_id)
            except Exception as exc:
                logger.warning(
                    "karakeep_crawl_result_fetch_failed",
                    extra={
                        "correlation_id": correlation_id,
                        "request_id": request_id,
                        "error": str(exc),
                    },
                )

        note = extract_summary_note(summary_data)

        if existing_bookmark is not None:
            bookmark, updated, _, error = await self._retry.run(
                lambda: client.update_bookmark(existing_bookmark.id, title=title, note=note),
                operation_name="update_bookmark",
                correlation_id=correlation_id,
            )
            if not updated or not bookmark:
                raise RuntimeError(f"Failed to update bookmark for summary {summary_id}: {error}")

            sync_id = await repository.async_upsert_sync_record(
                bsr_summary_id=summary_id,
                karakeep_bookmark_id=bookmark.id,
                url_hash=work_item.url_hash,
                sync_direction="bsr_to_karakeep",
                synced_at=datetime.now(UTC),
                bsr_modified_at=summary_data.get("updated_at"),
                karakeep_modified_at=bookmark.modified_at,
            )
        else:
            bookmark, created, _, error = await self._retry.run(
                lambda: client.create_bookmark(url=url, title=title, note=note),
                operation_name="create_bookmark",
                correlation_id=correlation_id,
            )
            if not created or not bookmark:
                raise RuntimeError(f"Failed to create bookmark for summary {summary_id}: {error}")

            sync_id = await repository.async_create_sync_record(
                bsr_summary_id=summary_id,
                karakeep_bookmark_id=bookmark.id,
                url_hash=work_item.url_hash,
                sync_direction="bsr_to_karakeep",
                synced_at=datetime.now(UTC),
                bsr_modified_at=summary_data.get("updated_at"),
                karakeep_modified_at=bookmark.modified_at,
            )

            if sync_id is None:
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

        metadata_errors, last_modified = await self._metadata.apply(
            client,
            bookmark=bookmark,
            summary_data=summary_data,
            correlation_id=correlation_id,
            counters=counters,
        )
        non_fatal_errors.extend(metadata_errors)

        if last_modified and last_modified != bookmark.modified_at:
            await repository.async_update_sync_timestamps(
                sync_id,
                karakeep_modified_at=last_modified,
            )

        return non_fatal_errors
