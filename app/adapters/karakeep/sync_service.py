"""Backward-compatible facade for Karakeep sync service.

The original implementation lived in this module. It has been split into small,
focused components under `app.adapters.karakeep.sync` to better follow Clean
Architecture and SOLID. This module re-exports the public surface area to avoid
churn in import paths.
"""

from __future__ import annotations

from app.adapters.karakeep.sync.constants import (
    BOOKMARK_PAGE_SIZE,
    DEFAULT_BACKOFF_FACTOR,
    DEFAULT_BASE_DELAY_SECONDS,
    DEFAULT_MAX_DELAY_SECONDS,
    DEFAULT_MAX_RETRIES,
    LEGACY_HASH_LENGTH,
    TAG_BSR_READ,
    TAG_BSR_SYNCED,
)
from app.adapters.karakeep.sync.datetime_utils import _ensure_datetime
from app.adapters.karakeep.sync.hashing import _check_hash_in_set, _url_hash
from app.adapters.karakeep.sync.protocols import (
    KarakeepClientFactory,
    KarakeepClientProtocol,
    KarakeepSyncRepository,
)
from app.adapters.karakeep.sync.service import KarakeepSyncService
from app.adapters.karakeep.sync.work_items import _SyncWorkItem

__all__ = [
    "BOOKMARK_PAGE_SIZE",
    "DEFAULT_BACKOFF_FACTOR",
    "DEFAULT_BASE_DELAY_SECONDS",
    "DEFAULT_MAX_DELAY_SECONDS",
    "DEFAULT_MAX_RETRIES",
    "LEGACY_HASH_LENGTH",
    "TAG_BSR_READ",
    "TAG_BSR_SYNCED",
    "KarakeepClientFactory",
    "KarakeepClientProtocol",
    "KarakeepSyncRepository",
    "KarakeepSyncService",
    "_SyncWorkItem",
    "_check_hash_in_set",
    "_ensure_datetime",
    "_url_hash",
]
