"""Metadata extraction and application for Karakeep bookmarks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.adapters.karakeep.models import KarakeepBookmark
from app.adapters.karakeep.sync.constants import TAG_BSR_READ

if TYPE_CHECKING:
    from datetime import datetime

    from app.adapters.karakeep.sync.protocols import KarakeepClientProtocol
    from app.adapters.karakeep.sync.retry import RetryExecutor

logger = logging.getLogger(__name__)


def extract_summary_url(summary_data: dict[str, Any]) -> str | None:
    request_data = summary_data.get("request_data", {})
    return request_data.get("normalized_url")


def extract_summary_note(summary_data: dict[str, Any]) -> str | None:
    json_payload = summary_data.get("json_payload")
    if not json_payload:
        return None
    return json_payload.get("tldr") or json_payload.get("summary_250")


def extract_topic_tags(summary_data: dict[str, Any], *, limit: int = 5) -> list[str]:
    json_payload = summary_data.get("json_payload")
    if not json_payload:
        return []
    topic_tags = json_payload.get("topic_tags", [])
    if len(topic_tags) > limit:
        logger.debug(
            "karakeep_truncating_tags",
            extra={"count": len(topic_tags), "limit": limit},
        )
    tags: list[str] = []
    for tag in topic_tags[:limit]:
        clean_tag = tag.lstrip("#").strip()
        if clean_tag:
            tags.append(clean_tag)
    return tags


def build_base_tags(summary_data: dict[str, Any], *, sync_tag: str) -> list[str]:
    tags = [sync_tag]
    if summary_data.get("is_read"):
        tags.append(TAG_BSR_READ)
    return tags


class BookmarkMetadataApplier:
    def __init__(self, retry: RetryExecutor, *, sync_tag: str) -> None:
        self._retry = retry
        self._sync_tag = sync_tag

    async def apply(
        self,
        client: KarakeepClientProtocol,
        *,
        bookmark: KarakeepBookmark,
        summary_data: dict[str, Any],
        correlation_id: str,
        counters: dict[str, int] | None = None,
    ) -> tuple[list[tuple[str, bool]], datetime | None]:
        non_fatal_errors: list[tuple[str, bool]] = []
        summary_id = summary_data.get("id")
        last_karakeep_modified_at = bookmark.modified_at

        if summary_data.get("is_favorited"):
            updated_bookmark, success, fav_retryable, fav_error = await self._retry.run(
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

        tags = build_base_tags(summary_data, sync_tag=self._sync_tag)
        tags.extend(extract_topic_tags(summary_data))

        if tags:
            updated_bookmark, success, tag_retryable, tag_error = await self._retry.run(
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

        return non_fatal_errors, last_karakeep_modified_at
