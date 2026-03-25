from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.application.use_cases.get_unread_summaries import GetUnreadSummariesUseCase
from app.application.use_cases.mark_summary_as_read import MarkSummaryAsReadUseCase
from app.application.use_cases.mark_summary_as_unread import MarkSummaryAsUnreadUseCase
from app.application.use_cases.search_topics import SearchTopicsUseCase
from app.di.repositories import (
    build_audit_log_repository,
    build_request_repository,
    build_rule_repository,
    build_summary_repository,
    build_tag_repository,
    build_topic_search_repository,
    build_webhook_repository,
)
from app.di.types import ApplicationServices
from app.infrastructure.messaging.event_bus import EventBus
from app.infrastructure.messaging.handlers.wiring import wire_event_handlers
from app.infrastructure.rules.collection_membership import SqliteCollectionMembershipAdapter
from app.infrastructure.rules.context import SqliteRuleContextAdapter
from app.infrastructure.rules.http_webhook_dispatcher import HttpWebhookDispatchAdapter
from app.infrastructure.rules.in_memory_rate_limiter import InMemoryRuleRateLimiter

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager


def build_application_services(
    db: DatabaseSessionManager,
    *,
    topic_search_service: Any | None = None,
    analytics_service: Any | None = None,
    telegram_client: Any | None = None,
    notification_service: Any | None = None,
    cache_service: Any | None = None,
    webhook_client: Any | None = None,
    webhook_url: str | None = None,
    vector_store: Any | None = None,
    embedding_generator: Any | None = None,
    push_notification_service: Any | None = None,
) -> ApplicationServices:
    summary_repository = build_summary_repository(db)
    request_repository = build_request_repository(db)
    event_bus = EventBus()
    wire_event_handlers(
        event_bus=event_bus,
        search_index_repository=build_topic_search_repository(db),
        audit_log_repository=build_audit_log_repository(db),
        request_repository=request_repository,
        summary_repository=summary_repository,
        rule_repository=build_rule_repository(db),
        tag_repository=build_tag_repository(db),
        collection_membership=SqliteCollectionMembershipAdapter(db),
        rule_context=SqliteRuleContextAdapter(db),
        webhook_dispatch_port=HttpWebhookDispatchAdapter(),
        rule_rate_limiter=InMemoryRuleRateLimiter(),
        analytics_service=analytics_service,
        telegram_client=telegram_client,
        notification_service=notification_service,
        cache_service=cache_service,
        webhook_client=webhook_client,
        webhook_url=webhook_url,
        embedding_generator=embedding_generator,
        vector_store=vector_store,
        push_notification_service=push_notification_service,
        webhook_repository=build_webhook_repository(db),
    )
    return ApplicationServices(
        unread_summaries=GetUnreadSummariesUseCase(summary_repository=summary_repository),
        mark_summary_as_read=MarkSummaryAsReadUseCase(summary_repository=summary_repository),
        mark_summary_as_unread=MarkSummaryAsUnreadUseCase(summary_repository=summary_repository),
        search_topics=SearchTopicsUseCase(topic_search_service) if topic_search_service else None,
        event_bus=event_bus,
    )
