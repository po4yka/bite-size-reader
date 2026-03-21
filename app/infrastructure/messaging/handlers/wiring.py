"""Wiring helper for event handlers."""

from __future__ import annotations

from typing import Any

from app.core.logging_utils import get_logger
from app.domain.events.request_events import RequestCompleted, RequestFailed
from app.domain.events.summary_events import SummaryCreated, SummaryMarkedAsRead
from app.domain.events.tag_events import TagAttached, TagDetached
from app.infrastructure.messaging.handlers.analytics import AnalyticsEventHandler
from app.infrastructure.messaging.handlers.audit_log import AuditLogEventHandler
from app.infrastructure.messaging.handlers.cache_invalidation import CacheInvalidationEventHandler
from app.infrastructure.messaging.handlers.embedding_generation import (
    EmbeddingGenerationEventHandler,
)
from app.infrastructure.messaging.handlers.notification import NotificationEventHandler
from app.infrastructure.messaging.handlers.push_notification import PushNotificationEventHandler
from app.infrastructure.messaging.handlers.rule_engine_handler import RuleEngineHandler
from app.infrastructure.messaging.handlers.search_index import SearchIndexEventHandler
from app.infrastructure.messaging.handlers.webhook import WebhookEventHandler
from app.infrastructure.messaging.handlers.webhook_dispatcher import WebhookDispatcher

logger = get_logger(__name__)


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
    push_notification_service: Any | None = None,
    request_repository: Any | None = None,
    webhook_repository: Any | None = None,
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
    event_bus.subscribe(TagAttached, search_index_handler.on_tag_attached)
    event_bus.subscribe(TagDetached, search_index_handler.on_tag_detached)
    event_bus.subscribe(SummaryCreated, audit_log_handler.on_summary_created)
    event_bus.subscribe(SummaryCreated, cache_handler.on_summary_created)
    event_bus.subscribe(SummaryCreated, webhook_handler.on_summary_created)
    if embedding_handler:
        event_bus.subscribe(SummaryCreated, embedding_handler.on_summary_created)

    push_handler: PushNotificationEventHandler | None = None
    if push_notification_service and summary_repository and request_repository:
        push_handler = PushNotificationEventHandler(
            push_service=push_notification_service,
            summary_repository=summary_repository,
            request_repository=request_repository,
        )
        event_bus.subscribe(SummaryCreated, push_handler.on_summary_created)

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

    # Rule engine handler (stateless -- always wired)
    rule_handler = RuleEngineHandler()
    event_bus.subscribe(SummaryCreated, rule_handler.on_summary_created)
    event_bus.subscribe(RequestCompleted, rule_handler.on_request_completed)
    event_bus.subscribe(RequestFailed, rule_handler.on_request_failed)
    event_bus.subscribe(TagAttached, rule_handler.on_tag_attached)
    event_bus.subscribe(TagDetached, rule_handler.on_tag_detached)

    # Per-user webhook dispatcher (additive alongside system-wide WebhookEventHandler)
    webhook_dispatcher: WebhookDispatcher | None = None
    if webhook_repository is not None:
        webhook_dispatcher = WebhookDispatcher(webhook_repository)
        event_bus.subscribe(SummaryCreated, webhook_dispatcher.on_summary_created)
        event_bus.subscribe(RequestCompleted, webhook_dispatcher.on_request_completed)
        event_bus.subscribe(RequestFailed, webhook_dispatcher.on_request_failed)
        event_bus.subscribe(TagAttached, webhook_dispatcher.on_tag_attached)
        event_bus.subscribe(TagDetached, webhook_dispatcher.on_tag_detached)

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
                "push_notifications": push_handler is not None,
                "rule_engine": True,
                "webhook_dispatcher": webhook_dispatcher is not None,
            },
        },
    )
