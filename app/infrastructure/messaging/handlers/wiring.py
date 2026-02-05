"""Wiring helper for event handlers."""

from __future__ import annotations

import logging
from typing import Any

from app.domain.events.request_events import RequestCompleted, RequestFailed
from app.domain.events.summary_events import SummaryCreated, SummaryMarkedAsRead
from app.infrastructure.messaging.handlers.analytics import AnalyticsEventHandler
from app.infrastructure.messaging.handlers.audit_log import AuditLogEventHandler
from app.infrastructure.messaging.handlers.cache_invalidation import CacheInvalidationEventHandler
from app.infrastructure.messaging.handlers.embedding_generation import (
    EmbeddingGenerationEventHandler,
)
from app.infrastructure.messaging.handlers.notification import NotificationEventHandler
from app.infrastructure.messaging.handlers.search_index import SearchIndexEventHandler
from app.infrastructure.messaging.handlers.webhook import WebhookEventHandler

logger = logging.getLogger(__name__)


def wire_event_handlers(
    event_bus: Any,
    database: Any,
    analytics_service: Any | None = None,
    telegram_client: Any | None = None,
    notification_service: Any | None = None,
    cache_service: Any | None = None,
    webhook_client: Any | None = None,
    webhook_url: str | None = None,
    embedding_generator: Any | None = None,
    vector_store: Any | None = None,
    summary_repository: Any | None = None,
) -> None:
    search_index_handler = SearchIndexEventHandler(database)
    analytics_handler = AnalyticsEventHandler(analytics_service)
    audit_log_handler = AuditLogEventHandler(database)

    notification_handler = NotificationEventHandler(telegram_client, notification_service)
    cache_handler = CacheInvalidationEventHandler(cache_service)
    webhook_handler = WebhookEventHandler(webhook_client, webhook_url)
    embedding_handler = (
        EmbeddingGenerationEventHandler(embedding_generator, summary_repository, vector_store)
        if embedding_generator and summary_repository
        else None
    )

    event_bus.subscribe(SummaryCreated, search_index_handler.on_summary_created)
    event_bus.subscribe(SummaryCreated, audit_log_handler.on_summary_created)
    event_bus.subscribe(SummaryCreated, cache_handler.on_summary_created)
    event_bus.subscribe(SummaryCreated, webhook_handler.on_summary_created)
    if embedding_handler:
        event_bus.subscribe(SummaryCreated, embedding_handler.on_summary_created)

    event_bus.subscribe(SummaryMarkedAsRead, search_index_handler.on_summary_marked_as_read)
    event_bus.subscribe(SummaryMarkedAsRead, analytics_handler.on_summary_marked_as_read)
    event_bus.subscribe(SummaryMarkedAsRead, cache_handler.on_summary_marked_as_read)

    event_bus.subscribe(RequestCompleted, analytics_handler.on_request_completed)
    event_bus.subscribe(RequestCompleted, audit_log_handler.on_request_completed)
    event_bus.subscribe(RequestCompleted, notification_handler.on_request_completed)
    event_bus.subscribe(RequestCompleted, cache_handler.on_request_completed)
    event_bus.subscribe(RequestCompleted, webhook_handler.on_request_completed)

    event_bus.subscribe(RequestFailed, analytics_handler.on_request_failed)
    event_bus.subscribe(RequestFailed, audit_log_handler.on_request_failed)
    event_bus.subscribe(RequestFailed, notification_handler.on_request_failed)
    event_bus.subscribe(RequestFailed, webhook_handler.on_request_failed)

    logger.info(
        "event_handlers_wired",
        extra={
            "summary_created_handlers": event_bus.get_handler_count(SummaryCreated),
            "summary_read_handlers": event_bus.get_handler_count(SummaryMarkedAsRead),
            "request_completed_handlers": event_bus.get_handler_count(RequestCompleted),
            "request_failed_handlers": event_bus.get_handler_count(RequestFailed),
            "optional_handlers_enabled": {
                "notifications": telegram_client is not None or notification_service is not None,
                "cache": cache_service is not None,
                "webhooks": webhook_client is not None and webhook_url is not None,
                "embeddings": embedding_generator is not None,
            },
        },
    )
