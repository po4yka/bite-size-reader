"""Dry-run preview logic for Karakeep sync."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.adapters.karakeep.client import KarakeepClientError
from app.adapters.karakeep.sync.hashing import _check_hash_in_set, _url_hash
from app.adapters.karakeep.sync.metadata import extract_summary_url
from app.core.url_utils import normalize_url, url_hash_sha256

if TYPE_CHECKING:
    from app.adapters.karakeep.models import KarakeepBookmark
    from app.adapters.karakeep.sync.cache import KarakeepBookmarkCache
    from app.adapters.karakeep.sync.protocols import KarakeepClientProtocol, KarakeepSyncRepository

logger = logging.getLogger(__name__)


class SyncPreviewer:
    def __init__(self, *, cache: KarakeepBookmarkCache) -> None:
        self._cache = cache

    async def preview(
        self,
        client: KarakeepClientProtocol,
        repository: KarakeepSyncRepository,
        *,
        user_id: int | None,
        limit: int | None,
        correlation_id: str,
    ) -> dict[str, Any]:
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
            karakeep_url_index = await self._cache.get_url_index(
                client, correlation_id=correlation_id
            )

            synced_hashes_bsr = await repository.async_get_synced_hashes_by_direction(
                "bsr_to_karakeep"
            )
            synced_hashes_kk = await repository.async_get_synced_hashes_by_direction(
                "karakeep_to_bsr"
            )

            summaries_data = await repository.async_get_summaries_for_sync(user_id=user_id)
            count = 0
            for summary_data in summaries_data:
                if limit and count >= limit:
                    break
                url = extract_summary_url(summary_data)
                if not url:
                    continue
                url_hash = _url_hash(url)

                if _check_hash_in_set(url_hash, synced_hashes_bsr):
                    preview["bsr_to_karakeep"]["would_skip"] += 1
                    continue

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

            existing_hashes = await repository.async_get_existing_request_hashes()
            count = 0

            async def process_preview_bookmark(
                normalized_url: str, bookmark: KarakeepBookmark
            ) -> bool:
                nonlocal count
                url_hash = _url_hash(bookmark.url or "")

                if _check_hash_in_set(url_hash, synced_hashes_kk):
                    preview["karakeep_to_bsr"]["would_skip"] += 1
                    return False

                dedupe = url_hash_sha256(normalized_url)
                if dedupe in existing_hashes:
                    preview["karakeep_to_bsr"]["already_exists_in_bsr"].append(
                        {"karakeep_id": bookmark.id, "url": bookmark.url}
                    )
                    preview["karakeep_to_bsr"]["would_skip"] += 1
                    return False

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

            cached = self._cache.cached_bookmarks()
            if cached is not None:
                for bookmark in cached:
                    if not bookmark.url:
                        continue
                    normalized_url = normalize_url(bookmark.url) or bookmark.url
                    if await process_preview_bookmark(normalized_url, bookmark):
                        break
            else:
                async for normalized_url, bookmark in self._cache.iter_bookmarks(
                    client, correlation_id=correlation_id
                ):
                    if await process_preview_bookmark(normalized_url, bookmark):
                        break

        except KarakeepClientError as exc:
            preview["errors"].append(f"Karakeep client error: {exc}")
        except Exception as exc:
            preview["errors"].append(f"Unexpected error: {exc}")

        return preview
