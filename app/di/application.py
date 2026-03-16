from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.application.use_cases.get_unread_summaries import GetUnreadSummariesUseCase
from app.application.use_cases.mark_summary_as_read import MarkSummaryAsReadUseCase
from app.application.use_cases.mark_summary_as_unread import MarkSummaryAsUnreadUseCase
from app.application.use_cases.search_topics import SearchTopicsUseCase
from app.di.repositories import build_summary_repository
from app.di.types import ApplicationServices
from app.infrastructure.messaging.event_bus import EventBus
from app.infrastructure.messaging.handlers.wiring import wire_event_handlers

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
) -> ApplicationServices:
    summary_repository = build_summary_repository(db)
    event_bus = EventBus()
    wire_event_handlers(
        event_bus=event_bus,
        database=db,
        analytics_service=analytics_service,
        telegram_client=telegram_client,
        notification_service=notification_service,
        cache_service=cache_service,
        webhook_client=webhook_client,
        webhook_url=webhook_url,
        embedding_generator=embedding_generator,
        vector_store=vector_store,
        summary_repository=summary_repository,
    )
    return ApplicationServices(
        unread_summaries=GetUnreadSummariesUseCase(summary_repository=summary_repository),
        mark_summary_as_read=MarkSummaryAsReadUseCase(summary_repository=summary_repository),
        mark_summary_as_unread=MarkSummaryAsUnreadUseCase(summary_repository=summary_repository),
        search_topics=SearchTopicsUseCase(topic_search_service) if topic_search_service else None,
        event_bus=event_bus,
    )
