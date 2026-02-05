"""Public re-exports for concrete event handlers.

Handler implementations live in `app.infrastructure.messaging.handlers`.
This module keeps backward-compatible import paths.
"""

from app.infrastructure.messaging.handlers.analytics import AnalyticsEventHandler
from app.infrastructure.messaging.handlers.audit_log import AuditLogEventHandler
from app.infrastructure.messaging.handlers.cache_invalidation import CacheInvalidationEventHandler
from app.infrastructure.messaging.handlers.embedding_generation import (
    EmbeddingGenerationEventHandler,
)
from app.infrastructure.messaging.handlers.notification import NotificationEventHandler
from app.infrastructure.messaging.handlers.search_index import SearchIndexEventHandler
from app.infrastructure.messaging.handlers.webhook import WebhookEventHandler
from app.infrastructure.messaging.handlers.wiring import wire_event_handlers

__all__ = [
    "AnalyticsEventHandler",
    "AuditLogEventHandler",
    "CacheInvalidationEventHandler",
    "EmbeddingGenerationEventHandler",
    "NotificationEventHandler",
    "SearchIndexEventHandler",
    "WebhookEventHandler",
    "wire_event_handlers",
]
