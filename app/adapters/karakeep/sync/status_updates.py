"""Status synchronization for already-synced items (read/favourite)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.adapters.karakeep.models import KarakeepBookmark
from app.adapters.karakeep.sync.constants import TAG_BSR_READ
from app.adapters.karakeep.sync.datetime_utils import _ensure_datetime

if TYPE_CHECKING:
    from app.adapters.karakeep.sync.cache import KarakeepBookmarkCache
    from app.adapters.karakeep.sync.protocols import KarakeepClientProtocol, KarakeepSyncRepository
    from app.adapters.karakeep.sync.retry import RetryExecutor

logger = logging.getLogger(__name__)


class StatusUpdateSynchronizer:
    def __init__(self, *, cache: KarakeepBookmarkCache, retry: RetryExecutor) -> None:
        self._cache = cache
        self._retry = retry

    async def sync(
        self,
        client: KarakeepClientProtocol,
        repository: KarakeepSyncRepository,
        *,
        correlation_id: str,
    ) -> dict[str, int | list[str]]:
        bsr_to_kk_updated = 0
        kk_to_bsr_updated = 0
        tags_added = 0
        tags_removed = 0
        favourites_updated = 0
        errors: list[str] = []

        logger.info("karakeep_status_sync_start", extra={"correlation_id": correlation_id})

        try:
            synced_items = await repository.async_get_synced_items_with_bookmark_and_summary()
            if not synced_items:
                logger.info(
                    "karakeep_status_sync_no_items", extra={"correlation_id": correlation_id}
                )
                return {
                    "bsr_to_karakeep_updated": 0,
                    "karakeep_to_bsr_updated": 0,
                    "tags_added": 0,
                    "tags_removed": 0,
                    "favourites_updated": 0,
                    "errors": errors,
                }

            karakeep_bookmarks = await self._cache.get_bookmarks(
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

                    summary_data = await repository.async_get_summary_by_id(summary_id)
                    if not summary_data:
                        continue

                    bookmark = karakeep_by_id.get(bookmark_id)
                    if not bookmark:
                        continue

                    kk_has_read_tag = any(t.name == TAG_BSR_READ for t in (bookmark.tags or []))
                    kk_fav = bookmark.favourited

                    bsr_read = summary_data.get("is_read", False)
                    bsr_fav = summary_data.get("is_favorited", False)

                    bsr_is_source = sync_record.get("sync_direction") == "bsr_to_karakeep"
                    summary_updated_at = _ensure_datetime(summary_data.get("updated_at"))
                    bookmark_updated_at = _ensure_datetime(bookmark.modified_at)
                    bsr_modified_at = _ensure_datetime(sync_record.get("bsr_modified_at"))
                    karakeep_modified_at = _ensure_datetime(sync_record.get("karakeep_modified_at"))

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
                        needs_update = False
                        tags_to_add: list[str] = []
                        tags_to_remove: list[str] = []
                        last_karakeep_modified_at = bookmark.modified_at

                        if bsr_read and not kk_has_read_tag:
                            tags_to_add.append(TAG_BSR_READ)
                            needs_update = True
                        elif not bsr_read and kk_has_read_tag:
                            for tag in bookmark.tags or []:
                                if tag.name == TAG_BSR_READ:
                                    tags_to_remove.append(tag.id)
                                    needs_update = True
                                    break

                        if bsr_fav != kk_fav:
                            updated, success, retryable, error = await self._retry.run(
                                lambda bid=bookmark.id, fav=bsr_fav: client.update_bookmark(  # type: ignore[misc]
                                    bid, favourited=fav, correlation_id=correlation_id
                                ),
                                operation_name="update_bookmark_favourite",
                                correlation_id=correlation_id,
                            )
                            if success:
                                favourites_updated += 1
                                needs_update = True
                                if isinstance(updated, KarakeepBookmark) and updated.modified_at:
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

                        if tags_to_add:
                            updated, success, retryable, error = await self._retry.run(
                                lambda bid=bookmark.id, tags=tags_to_add: client.attach_tags(  # type: ignore[misc]
                                    bid, tags, correlation_id=correlation_id
                                ),
                                operation_name="attach_tags",
                                correlation_id=correlation_id,
                            )
                            if success:
                                tags_added += len(tags_to_add)
                                needs_update = True
                                if isinstance(updated, KarakeepBookmark) and updated.modified_at:
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
                            _, success, retryable, error = await self._retry.run(
                                lambda bid=bookmark.id, tid=tag_id: client.detach_tag(  # type: ignore[misc]
                                    bid, tid, correlation_id=correlation_id
                                ),
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
                            await repository.async_update_sync_timestamps(
                                sync_id,
                                bsr_modified_at=summary_data.get("updated_at"),
                                karakeep_modified_at=last_karakeep_modified_at or datetime.now(UTC),
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

                    elif kk_has_read_tag != bsr_read or kk_fav != bsr_fav:
                        await repository.async_update_summary_status(
                            summary_id,
                            is_read=kk_has_read_tag,
                            is_favorited=kk_fav,
                        )

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

                except Exception as exc:
                    error_msg = f"Failed to sync status for {sync_record.get('id')}: {exc}"
                    errors.append(error_msg)
                    logger.warning(
                        "karakeep_status_sync_item_failed",
                        extra={
                            "correlation_id": correlation_id,
                            "sync_id": sync_record.get("id"),
                            "error": str(exc),
                        },
                    )

        except Exception as exc:
            errors.append(f"Status sync failed: {exc}")
            logger.exception(
                "karakeep_status_sync_failed", extra={"correlation_id": correlation_id}
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
