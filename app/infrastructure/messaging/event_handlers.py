"""Compatibility module for historic event-handler import paths."""

from __future__ import annotations

from typing import Any

from app.core.module_compat import load_compat_symbol

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "AnalyticsEventHandler": (
        "app.infrastructure.messaging.handlers.analytics",
        "AnalyticsEventHandler",
    ),
    "AuditLogEventHandler": (
        "app.infrastructure.messaging.handlers.audit_log",
        "AuditLogEventHandler",
    ),
    "CacheInvalidationEventHandler": (
        "app.infrastructure.messaging.handlers.cache_invalidation",
        "CacheInvalidationEventHandler",
    ),
    "EmbeddingGenerationEventHandler": (
        "app.infrastructure.messaging.handlers.embedding_generation",
        "EmbeddingGenerationEventHandler",
    ),
    "NotificationEventHandler": (
        "app.infrastructure.messaging.handlers.notification",
        "NotificationEventHandler",
    ),
    "SearchIndexEventHandler": (
        "app.infrastructure.messaging.handlers.search_index",
        "SearchIndexEventHandler",
    ),
    "WebhookEventHandler": ("app.infrastructure.messaging.handlers.webhook", "WebhookEventHandler"),
    "wire_event_handlers": ("app.infrastructure.messaging.handlers.wiring", "wire_event_handlers"),
}


def __getattr__(name: str) -> Any:
    return load_compat_symbol(
        module_name=__name__,
        attribute_name=name,
        export_map=_COMPAT_EXPORTS,
        namespace=globals(),
    )
