"""Public Karakeep sync service composed of small use-case classes."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from app.adapters.karakeep.client import KarakeepClient, KarakeepClientError
from app.adapters.karakeep.models import FullSyncResult, SyncResult
from app.adapters.karakeep.sync.bsr_to_karakeep import BsrToKarakeepSyncer
from app.adapters.karakeep.sync.cache import KarakeepBookmarkCache
from app.adapters.karakeep.sync.constants import TAG_BSR_SYNCED
from app.adapters.karakeep.sync.errors import record_error
from app.adapters.karakeep.sync.karakeep_to_bsr import KarakeepToBsrSyncer
from app.adapters.karakeep.sync.metadata import BookmarkMetadataApplier
from app.adapters.karakeep.sync.preview import SyncPreviewer
from app.adapters.karakeep.sync.retry import RetryExecutor
from app.adapters.karakeep.sync.status_updates import StatusUpdateSynchronizer
from app.core.logging_utils import generate_correlation_id
from app.utils.retry_utils import is_transient_error

if TYPE_CHECKING:
    from datetime import datetime

    from app.adapters.karakeep.models import KarakeepBookmark
    from app.adapters.karakeep.sync.protocols import (
        KarakeepClientFactory,
        KarakeepClientProtocol,
        KarakeepSyncRepository,
    )

logger = logging.getLogger(__name__)


class KarakeepSyncService:
    """Bidirectional sync service between BSR and Karakeep.

    This is a thin orchestrator that delegates business rules to focused
    collaborators (Clean Architecture + SOLID).
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        sync_tag: str = TAG_BSR_SYNCED,
        repository: KarakeepSyncRepository | None = None,
        client_factory: KarakeepClientFactory | None = None,
    ) -> None:
        self.api_url = api_url
        self.api_key = api_key
        self.sync_tag = sync_tag
        self._repository = repository
        self._client_factory = client_factory or KarakeepClient

        self._cache = KarakeepBookmarkCache()
        self._retry = RetryExecutor()
        self._metadata = BookmarkMetadataApplier(self._retry, sync_tag=self.sync_tag)
        self._bsr_to_kk = BsrToKarakeepSyncer(
            cache=self._cache, retry=self._retry, metadata_applier=self._metadata
        )
        self._kk_to_bsr = KarakeepToBsrSyncer(cache=self._cache)
        self._previewer = SyncPreviewer(cache=self._cache)
        self._status_sync = StatusUpdateSynchronizer(cache=self._cache, retry=self._retry)

    def _require_repository(self) -> KarakeepSyncRepository:
        if not self._repository:
            raise RuntimeError("Repository not configured for sync service")
        return self._repository

    @asynccontextmanager
    async def _cache_scope(self) -> Any:
        async with self._cache.scope():
            yield

    async def _ensure_healthy(self, client: KarakeepClientProtocol, errors: list[str]) -> bool:
        if not await client.health_check():
            errors.append("Karakeep API health check failed")
            return False
        return True

    async def sync_bsr_to_karakeep(
        self,
        user_id: int | None = None,
        limit: int | None = None,
        force: bool = False,
    ) -> SyncResult:
        repository = self._require_repository()
        correlation_id = generate_correlation_id()
        self._cache.clear_if_not_reusing()

        result = SyncResult(direction="bsr_to_karakeep")
        try:
            async with self._client_factory(self.api_url, self.api_key) as client:
                if not await self._ensure_healthy(client, result.errors):
                    record_error(result, "Karakeep API health check failed", retryable=True)
                    logger.error(
                        "karakeep_sync_health_check_failed",
                        extra={"correlation_id": correlation_id},
                    )
                    return result
                return await self._bsr_to_kk.sync(
                    client,
                    repository,
                    user_id=user_id,
                    limit=limit,
                    force=force,
                    correlation_id=correlation_id,
                )
        except KarakeepClientError as exc:
            record_error(result, f"Karakeep client error: {exc}", is_transient_error(exc))
            return result

    async def sync_karakeep_to_bsr(
        self,
        user_id: int,
        limit: int | None = None,
    ) -> SyncResult:
        repository = self._require_repository()
        correlation_id = generate_correlation_id()
        self._cache.clear_if_not_reusing()

        result = SyncResult(direction="karakeep_to_bsr")
        try:
            async with self._client_factory(self.api_url, self.api_key) as client:
                if not await self._ensure_healthy(client, result.errors):
                    record_error(result, "Karakeep API health check failed", retryable=True)
                    logger.error(
                        "karakeep_sync_health_check_failed",
                        extra={"correlation_id": correlation_id},
                    )
                    return result
                return await self._kk_to_bsr.sync(
                    client,
                    repository,
                    user_id=user_id,
                    limit=limit,
                    correlation_id=correlation_id,
                )
        except KarakeepClientError as exc:
            record_error(result, f"Karakeep client error: {exc}", is_transient_error(exc))
            return result

    async def run_full_sync(
        self,
        user_id: int | None = None,
        limit: int | None = None,
        force: bool = False,
    ) -> FullSyncResult:
        start_time = time.time()
        correlation_id = generate_correlation_id()

        async with self._cache_scope():
            bsr_result = await self.sync_bsr_to_karakeep(user_id=user_id, limit=limit, force=force)

            if user_id:
                karakeep_result = await self.sync_karakeep_to_bsr(user_id=user_id, limit=limit)
            else:
                karakeep_result = SyncResult(direction="karakeep_to_bsr")
                karakeep_result.errors.append("Skipped: user_id required for Karakeep->BSR sync")

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
                "correlation_id": correlation_id,
                "bsr_to_karakeep": bsr_result.items_synced,
                "karakeep_to_bsr": karakeep_result.items_synced,
                "status_updates_bsr_to_kk": status_result["bsr_to_karakeep_updated"],
                "status_updates_kk_to_bsr": status_result["karakeep_to_bsr_updated"],
                "total_duration": total_duration,
            },
        )
        return result

    async def get_sync_status(self) -> dict[str, Any]:
        repository = self._require_repository()
        return await repository.async_get_sync_stats()

    async def preview_sync(
        self,
        user_id: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        repository = self._require_repository()
        correlation_id = generate_correlation_id()
        self._cache.clear_if_not_reusing()

        errors: list[str] = []
        preview: dict[str, Any] = {
            "bsr_to_karakeep": {
                "would_sync": [],
                "would_skip": 0,
                "already_exists_in_karakeep": [],
            },
            "karakeep_to_bsr": {"would_sync": [], "would_skip": 0, "already_exists_in_bsr": []},
            "errors": errors,
        }

        try:
            async with self._client_factory(self.api_url, self.api_key) as client:
                if not await self._ensure_healthy(client, errors):
                    return preview
                return await self._previewer.preview(
                    client,
                    repository,
                    user_id=user_id,
                    limit=limit,
                    correlation_id=correlation_id,
                )
        except KarakeepClientError as exc:
            errors.append(f"Karakeep client error: {exc}")
            return preview

    async def sync_status_updates(self) -> dict[str, int | list[str]]:
        repository = self._require_repository()
        correlation_id = generate_correlation_id()
        self._cache.clear_if_not_reusing()

        errors: list[str] = []
        try:
            async with self._client_factory(self.api_url, self.api_key) as client:
                if not await self._ensure_healthy(client, errors):
                    logger.error(
                        "karakeep_status_sync_health_check_failed",
                        extra={"correlation_id": correlation_id},
                    )
                    return {
                        "bsr_to_karakeep_updated": 0,
                        "karakeep_to_bsr_updated": 0,
                        "tags_added": 0,
                        "tags_removed": 0,
                        "favourites_updated": 0,
                        "errors": errors,
                    }
                return await self._status_sync.sync(
                    client,
                    repository,
                    correlation_id=correlation_id,
                )
        except Exception as exc:
            errors.append(f"Status sync failed: {exc}")
            logger.exception(
                "karakeep_status_sync_failed", extra={"correlation_id": correlation_id}
            )
            return {
                "bsr_to_karakeep_updated": 0,
                "karakeep_to_bsr_updated": 0,
                "tags_added": 0,
                "tags_removed": 0,
                "favourites_updated": 0,
                "errors": errors,
            }

    async def _apply_bookmark_metadata(
        self,
        client: KarakeepClientProtocol,
        *,
        bookmark: KarakeepBookmark,
        summary_data: dict[str, Any],
        correlation_id: str,
        counters: dict[str, int] | None = None,
    ) -> tuple[list[tuple[str, bool]], datetime | None]:
        return await self._metadata.apply(
            client,
            bookmark=bookmark,
            summary_data=summary_data,
            correlation_id=correlation_id,
            counters=counters,
        )
