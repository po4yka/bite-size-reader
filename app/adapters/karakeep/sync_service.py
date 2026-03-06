"""Compatibility module for historic `app.adapters.karakeep.sync_service` imports."""

from __future__ import annotations

from typing import Any

from app.core.module_compat import load_compat_symbol

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "BOOKMARK_PAGE_SIZE": ("app.adapters.karakeep.sync.constants", "BOOKMARK_PAGE_SIZE"),
    "DEFAULT_BACKOFF_FACTOR": ("app.adapters.karakeep.sync.constants", "DEFAULT_BACKOFF_FACTOR"),
    "DEFAULT_BASE_DELAY_SECONDS": (
        "app.adapters.karakeep.sync.constants",
        "DEFAULT_BASE_DELAY_SECONDS",
    ),
    "DEFAULT_MAX_DELAY_SECONDS": (
        "app.adapters.karakeep.sync.constants",
        "DEFAULT_MAX_DELAY_SECONDS",
    ),
    "DEFAULT_MAX_RETRIES": ("app.adapters.karakeep.sync.constants", "DEFAULT_MAX_RETRIES"),
    "LEGACY_HASH_LENGTH": ("app.adapters.karakeep.sync.constants", "LEGACY_HASH_LENGTH"),
    "TAG_BSR_READ": ("app.adapters.karakeep.sync.constants", "TAG_BSR_READ"),
    "TAG_BSR_SYNCED": ("app.adapters.karakeep.sync.constants", "TAG_BSR_SYNCED"),
    "KarakeepClientFactory": ("app.adapters.karakeep.sync.protocols", "KarakeepClientFactory"),
    "KarakeepClientProtocol": ("app.adapters.karakeep.sync.protocols", "KarakeepClientProtocol"),
    "KarakeepSyncRepository": ("app.adapters.karakeep.sync.protocols", "KarakeepSyncRepository"),
    "KarakeepSyncService": ("app.adapters.karakeep.sync.service", "KarakeepSyncService"),
    "_SyncWorkItem": ("app.adapters.karakeep.sync.work_items", "_SyncWorkItem"),
    "_check_hash_in_set": ("app.adapters.karakeep.sync.hashing", "_check_hash_in_set"),
    "_ensure_datetime": ("app.adapters.karakeep.sync.datetime_utils", "_ensure_datetime"),
    "_url_hash": ("app.adapters.karakeep.sync.hashing", "_url_hash"),
}


def __getattr__(name: str) -> Any:
    return load_compat_symbol(
        module_name=__name__,
        attribute_name=name,
        export_map=_COMPAT_EXPORTS,
        namespace=globals(),
    )
