"""Protocol definitions (ports) for Karakeep sync.

Keeping these as Protocols helps isolate the sync orchestration from the
concrete persistence and HTTP implementations (DIP).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager
    from datetime import datetime

    from app.adapters.karakeep.models import KarakeepBookmark


class KarakeepClientProtocol(Protocol):
    async def health_check(self) -> bool: ...

    async def get_bookmarks(self, *, limit: int, cursor: str | None = None) -> Any: ...

    async def get_all_bookmarks(self) -> list[KarakeepBookmark]: ...

    async def create_bookmark(
        self, *, url: str, title: str | None, note: str | None
    ) -> KarakeepBookmark: ...

    async def update_bookmark(
        self,
        bookmark_id: str,
        *,
        title: str | None = None,
        note: str | None = None,
        archived: bool | None = None,
        favourited: bool | None = None,
    ) -> KarakeepBookmark: ...

    async def attach_tags(self, bookmark_id: str, tags: list[str]) -> None: ...

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

    async def async_delete_all_sync_records(self, direction: str | None = None) -> int: ...

    async def async_upsert_sync_record(
        self,
        *,
        bsr_summary_id: int | None = None,
        karakeep_bookmark_id: str | None = None,
        url_hash: str,
        sync_direction: str,
        synced_at: datetime | None = None,
        bsr_modified_at: datetime | None = None,
        karakeep_modified_at: datetime | None = None,
    ) -> int: ...
