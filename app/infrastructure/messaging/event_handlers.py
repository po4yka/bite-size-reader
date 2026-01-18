"""Real event handlers for domain events.

These handlers demonstrate how to use the event bus to implement side effects
and cross-cutting concerns in a decoupled way.
"""

import logging
from typing import Any

from app.domain.events.request_events import RequestCompleted, RequestFailed
from app.domain.events.summary_events import SummaryCreated, SummaryMarkedAsRead
from app.infrastructure.persistence.sqlite.repositories.audit_log_repository import (
    SqliteAuditLogRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.topic_search_repository import (
    SqliteTopicSearchRepositoryAdapter,
)

logger = logging.getLogger(__name__)


class EmbeddingGenerationEventHandler:
    """Event handler for generating vector embeddings for summaries.

    This handler responds to summary creation events and asynchronously
    generates embeddings for semantic search.
    """

    def __init__(
        self,
        embedding_generator: Any,
        summary_repository: SqliteSummaryRepositoryAdapter,
        vector_store: Any | None = None,
    ) -> None:
        """Initialize the handler.

        Args:
            embedding_generator: SummaryEmbeddingGenerator instance.
            summary_repository: Repository for summary retrieval.
            vector_store: Optional ChromaVectorStore for syncing embeddings.

        """
        self._generator = embedding_generator
        self._summary_repo = summary_repository
        self._vector_store = vector_store

    async def on_summary_created(self, event: SummaryCreated) -> None:
        """Generate embedding when a new summary is created.

        Args:
            event: SummaryCreated domain event.

        """
        logger.info(
            "generating_embedding_for_new_summary",
            extra={
                "summary_id": event.summary_id,
                "request_id": event.request_id,
            },
        )

        try:
            # Generate embedding asynchronously
            # This is a background task - failures are logged but don't block
            success = await self._generator.generate_embedding_for_request(
                request_id=event.request_id,
                force=False,
            )

            if success:
                logger.info(
                    "embedding_generated_successfully",
                    extra={
                        "summary_id": event.summary_id,
                        "request_id": event.request_id,
                    },
                )
            else:
                logger.debug(
                    "embedding_generation_skipped",
                    extra={
                        "summary_id": event.summary_id,
                        "request_id": event.request_id,
                        "reason": "already_exists_or_empty",
                    },
                )

            await self._sync_vector_store(event.request_id)

        except Exception as e:
            # Log error but don't fail - embedding generation is not critical
            logger.exception(
                "embedding_generation_failed",
                extra={
                    "summary_id": event.summary_id,
                    "request_id": event.request_id,
                    "error": str(e),
                },
            )

    async def _sync_vector_store(self, request_id: int) -> None:
        """Sync the latest embedding to the vector store if configured."""

        if not self._vector_store:
            return

        embedding_service = getattr(self._generator, "embedding_service", None)

        if embedding_service is None:
            logger.warning(
                "vector_store_sync_unavailable",
                extra={"request_id": request_id, "reason": "missing_dependencies"},
            )
            return

        summary = await self._summary_repo.async_get_summary_by_request(request_id)
        if not summary:
            logger.info(
                "vector_store_delete_missing_summary",
                extra={"request_id": request_id},
            )
            self._vector_store.delete_by_request_id(request_id)
            return

        payload = summary.get("json_payload")
        summary_id = summary.get("id")

        if not payload or not summary_id:
            logger.info(
                "vector_store_delete_empty_payload",
                extra={"request_id": request_id, "summary_id": summary_id},
            )
            self._vector_store.delete_by_request_id(request_id)
            return

        from app.services.metadata_builder import MetadataBuilder

        user_scope = getattr(self._vector_store, "user_scope", None) or "public"
        environment = getattr(self._vector_store, "environment", None) or "dev"

        chunk_windows = MetadataBuilder.prepare_chunk_windows_for_upsert(
            request_id=request_id,
            summary_id=summary_id,
            payload=payload,
            language=self._determine_language(summary),
            user_scope=user_scope,
            environment=environment,
        )

        vectors: list[list[float]] = []
        metadatas: list[dict[str, Any]] = []

        if chunk_windows:
            for text, metadata in chunk_windows:
                embedding = await embedding_service.generate_embedding(
                    text, language=metadata.get("language")
                )
                vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
                vectors.append(vector)
                metadatas.append(metadata)
        else:
            text, metadata = MetadataBuilder.prepare_for_upsert(
                request_id=request_id,
                summary_id=summary_id,
                payload=payload,
                language=self._determine_language(summary),
                user_scope=user_scope,
                environment=environment,
                summary_row=summary,
            )

            if not text:
                logger.info(
                    "vector_store_delete_empty_note",
                    extra={"request_id": request_id, "summary_id": summary_id},
                )
                self._vector_store.delete_by_request_id(request_id)
                return

            embedding = await embedding_service.generate_embedding(
                text, language=metadata.get("language")
            )
            vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
            vectors.append(vector)
            metadatas.append(metadata)

        if not vectors:
            logger.info(
                "vector_store_delete_empty_note",
                extra={"request_id": request_id, "summary_id": summary_id},
            )
            self._vector_store.delete_by_request_id(request_id)
            return

        self._vector_store.upsert_notes(vectors, metadatas)

        logger.info(
            "vector_store_synced",
            extra={
                "request_id": request_id,
                "summary_id": summary_id,
                "metadata_keys": sorted(metadatas[0].keys()) if metadatas else [],
                "vector_count": len(vectors),
            },
        )

    @staticmethod
    def _determine_language(summary: dict[str, Any]) -> str | None:
        if not summary:
            return None

        language = summary.get("lang") or summary.get("language")
        if language:
            return language

        request_data = summary.get("request") or {}
        if isinstance(request_data, dict):
            return request_data.get("lang_detected")
        return None


class SearchIndexEventHandler:
    """Event handler for updating the full-text search index.

    This handler responds to summary-related events and updates the FTS index
    to keep search functionality in sync with the database.
    """

    def __init__(self, database: Any) -> None:
        """Initialize the handler.

        Args:
            database: Database instance (session manager) or repository.

        """
        if isinstance(database, SqliteTopicSearchRepositoryAdapter):
            self._repo = database
        else:
            self._repo = SqliteTopicSearchRepositoryAdapter(database)

    async def on_summary_created(self, event: SummaryCreated) -> None:
        """Update search index when a new summary is created.

        Args:
            event: SummaryCreated domain event.

        """
        logger.info(
            "updating_search_index_for_new_summary",
            extra={
                "summary_id": event.summary_id,
                "request_id": event.request_id,
                "language": event.language,
            },
        )

        try:
            # Rebuild search index for this request
            # This ensures the new summary is searchable
            await self._repo.async_refresh_index(event.request_id)

            logger.debug(
                "search_index_updated",
                extra={"request_id": event.request_id, "summary_id": event.summary_id},
            )

        except Exception as e:
            # Log error but don't fail - search index update is not critical
            logger.exception(
                "search_index_update_failed",
                extra={
                    "summary_id": event.summary_id,
                    "request_id": event.request_id,
                    "error": str(e),
                },
            )

    async def on_summary_marked_as_read(self, event: SummaryMarkedAsRead) -> None:
        """Handle search index when summary is marked as read.

        Could be used to deprioritize read summaries in search results.

        Args:
            event: SummaryMarkedAsRead domain event.

        """
        logger.debug(
            "summary_marked_as_read_event",
            extra={"summary_id": event.summary_id},
        )

        # Optional: Update search index to deprioritize read summaries
        # For now, just log the event


class AnalyticsEventHandler:
    """Event handler for tracking analytics.

    This handler responds to various events and sends analytics data
    to external analytics services.
    """

    def __init__(self, analytics_service: Any | None = None) -> None:
        """Initialize the handler.

        Args:
            analytics_service: Optional analytics service client.

        """
        self._analytics = analytics_service

    async def on_request_completed(self, event: RequestCompleted) -> None:
        """Track successful request completion.

        Args:
            event: RequestCompleted domain event.

        """
        logger.info(
            "request_completed_analytics",
            extra={
                "request_id": event.request_id,
                "summary_id": event.summary_id,
                "occurred_at": event.occurred_at.isoformat(),
            },
        )

        if self._analytics:
            try:
                # Send to analytics service
                await self._analytics.track(
                    "request_completed",
                    {
                        "request_id": event.request_id,
                        "summary_id": event.summary_id,
                        "timestamp": event.occurred_at.isoformat(),
                    },
                )
            except Exception as e:
                logger.warning(
                    "analytics_tracking_failed",
                    extra={"event": "request_completed", "error": str(e)},
                )

    async def on_request_failed(self, event: RequestFailed) -> None:
        """Track failed requests.

        Args:
            event: RequestFailed domain event.

        """
        logger.warning(
            "request_failed_analytics",
            extra={
                "request_id": event.request_id,
                "error_message": event.error_message,
                "occurred_at": event.occurred_at.isoformat(),
            },
        )

        if self._analytics:
            try:
                # Send to analytics service
                await self._analytics.track(
                    "request_failed",
                    {
                        "request_id": event.request_id,
                        "error_message": event.error_message,
                        "timestamp": event.occurred_at.isoformat(),
                    },
                )
            except Exception as e:
                logger.warning(
                    "analytics_tracking_failed",
                    extra={"event": "request_failed", "error": str(e)},
                )

    async def on_summary_marked_as_read(self, event: SummaryMarkedAsRead) -> None:
        """Track when users mark summaries as read.

        Args:
            event: SummaryMarkedAsRead domain event.

        """
        logger.debug(
            "summary_read_analytics",
            extra={"summary_id": event.summary_id},
        )

        if self._analytics:
            try:
                await self._analytics.track(
                    "summary_marked_as_read",
                    {
                        "summary_id": event.summary_id,
                        "timestamp": event.occurred_at.isoformat(),
                    },
                )
            except Exception as e:
                logger.warning(
                    "analytics_tracking_failed",
                    extra={"event": "summary_marked_as_read", "error": str(e)},
                )


class AuditLogEventHandler:
    """Event handler for comprehensive audit logging.

    This handler logs all domain events to the audit log for compliance
    and debugging purposes.
    """

    def __init__(self, database: Any) -> None:
        """Initialize the handler.

        Args:
            database: Database instance or repository.

        """
        if isinstance(database, SqliteAuditLogRepositoryAdapter):
            self._repo = database
        else:
            self._repo = SqliteAuditLogRepositoryAdapter(database)

    async def on_summary_created(self, event: SummaryCreated) -> None:
        """Audit log summary creation.

        Args:
            event: SummaryCreated domain event.

        """
        try:
            await self._repo.async_insert_audit_log(
                log_level="INFO",
                event_type="summary_created",
                details={
                    "summary_id": event.summary_id,
                    "request_id": event.request_id,
                    "language": event.language,
                    "has_insights": event.has_insights,
                    "timestamp": event.occurred_at.isoformat(),
                },
            )
        except Exception as e:
            logger.warning(
                "audit_log_failed",
                extra={"event_type": "summary_created", "error": str(e)},
            )

    async def on_request_completed(self, event: RequestCompleted) -> None:
        """Audit log request completion.

        Args:
            event: RequestCompleted domain event.

        """
        try:
            await self._repo.async_insert_audit_log(
                log_level="INFO",
                event_type="request_completed",
                details={
                    "request_id": event.request_id,
                    "summary_id": event.summary_id,
                    "timestamp": event.occurred_at.isoformat(),
                },
            )
        except Exception as e:
            logger.warning(
                "audit_log_failed",
                extra={"event_type": "request_completed", "error": str(e)},
            )

    async def on_request_failed(self, event: RequestFailed) -> None:
        """Audit log request failure.

        Args:
            event: RequestFailed domain event.

        """
        try:
            await self._repo.async_insert_audit_log(
                log_level="ERROR",
                event_type="request_failed",
                details={
                    "request_id": event.request_id,
                    "error_message": event.error_message,
                    "error_details": event.error_details,
                    "timestamp": event.occurred_at.isoformat(),
                },
            )
        except Exception as e:
            logger.warning(
                "audit_log_failed",
                extra={"event_type": "request_failed", "error": str(e)},
            )


class NotificationEventHandler:
    """Event handler for sending user notifications.

    This handler responds to domain events and sends notifications to users
    via various channels (Telegram, email, push notifications, etc.).
    """

    def __init__(
        self, telegram_client: Any | None = None, notification_service: Any | None = None
    ) -> None:
        """Initialize the handler.

        Args:
            telegram_client: Optional Telegram client for sending messages.
            notification_service: Optional notification service for other channels.

        """
        self._telegram = telegram_client
        self._notification_service = notification_service

    async def on_request_completed(self, event: RequestCompleted) -> None:
        """Notify user when their request is completed.

        Args:
            event: RequestCompleted domain event.

        """
        logger.debug(
            "request_completed_notification",
            extra={
                "request_id": event.request_id,
                "summary_id": event.summary_id,
            },
        )

        # Example: Send notification via Telegram
        if self._telegram:
            try:
                # In a real implementation, you would:
                # 1. Look up the user's chat_id from the request_id
                # 2. Format a nice notification message
                # 3. Send it via self._telegram.send_message(chat_id, message)
                logger.debug(
                    "notification_would_be_sent",
                    extra={
                        "request_id": event.request_id,
                        "channel": "telegram",
                    },
                )
            except Exception as e:
                logger.warning(
                    "notification_send_failed",
                    extra={
                        "request_id": event.request_id,
                        "channel": "telegram",
                        "error": str(e),
                    },
                )

        # Example: Send via other notification services
        if self._notification_service:
            try:
                await self._notification_service.send(
                    "request_completed",
                    {
                        "request_id": event.request_id,
                        "summary_id": event.summary_id,
                        "timestamp": event.occurred_at.isoformat(),
                    },
                )
            except Exception as e:
                logger.warning(
                    "notification_send_failed",
                    extra={
                        "request_id": event.request_id,
                        "channel": "notification_service",
                        "error": str(e),
                    },
                )

    async def on_request_failed(self, event: RequestFailed) -> None:
        """Notify user when their request fails.

        Args:
            event: RequestFailed domain event.

        """
        logger.debug(
            "request_failed_notification",
            extra={
                "request_id": event.request_id,
                "error_message": event.error_message,
            },
        )

        # In production, you might want to notify users about failures
        # For now, just log it
        if self._telegram:
            try:
                logger.debug(
                    "failure_notification_would_be_sent",
                    extra={
                        "request_id": event.request_id,
                        "channel": "telegram",
                    },
                )
            except Exception as e:
                logger.warning(
                    "notification_send_failed",
                    extra={
                        "request_id": event.request_id,
                        "error": str(e),
                    },
                )


class CacheInvalidationEventHandler:
    """Event handler for cache invalidation.

    This handler responds to data change events and invalidates relevant
    caches to ensure data consistency.
    """

    def __init__(self, cache_service: Any | None = None) -> None:
        """Initialize the handler.

        Args:
            cache_service: Optional cache service (Redis, Memcached, etc.).

        """
        self._cache = cache_service

    async def on_summary_created(self, event: SummaryCreated) -> None:
        """Invalidate summary-related caches when a new summary is created.

        Args:
            event: SummaryCreated domain event.

        """
        logger.debug(
            "invalidating_summary_cache",
            extra={
                "summary_id": event.summary_id,
                "request_id": event.request_id,
            },
        )

        if self._cache:
            try:
                # Invalidate caches related to this summary/request
                cache_keys = [
                    f"summary:{event.summary_id}",
                    f"request:{event.request_id}",
                    f"request:{event.request_id}:summary",
                    "summaries:unread",  # Invalidate unread list
                    "summaries:recent",  # Invalidate recent summaries list
                ]

                for key in cache_keys:
                    await self._cache.delete(key)

                logger.debug(
                    "cache_invalidated",
                    extra={
                        "summary_id": event.summary_id,
                        "keys_invalidated": len(cache_keys),
                    },
                )

            except Exception as e:
                logger.warning(
                    "cache_invalidation_failed",
                    extra={
                        "summary_id": event.summary_id,
                        "error": str(e),
                    },
                )

    async def on_summary_marked_as_read(self, event: SummaryMarkedAsRead) -> None:
        """Invalidate caches when a summary is marked as read.

        Args:
            event: SummaryMarkedAsRead domain event.

        """
        logger.debug(
            "invalidating_read_status_cache",
            extra={"summary_id": event.summary_id},
        )

        if self._cache:
            try:
                # Invalidate read status caches
                cache_keys = [
                    f"summary:{event.summary_id}",
                    f"summary:{event.summary_id}:read_status",
                    "summaries:unread",  # User's unread list changed
                ]

                for key in cache_keys:
                    await self._cache.delete(key)

                logger.debug(
                    "cache_invalidated",
                    extra={
                        "summary_id": event.summary_id,
                        "keys_invalidated": len(cache_keys),
                    },
                )

            except Exception as e:
                logger.warning(
                    "cache_invalidation_failed",
                    extra={
                        "summary_id": event.summary_id,
                        "error": str(e),
                    },
                )

    async def on_request_completed(self, event: RequestCompleted) -> None:
        """Invalidate caches when a request is completed.

        Args:
            event: RequestCompleted domain event.

        """
        logger.debug(
            "invalidating_request_cache",
            extra={"request_id": event.request_id},
        )

        if self._cache:
            try:
                # Invalidate request status caches
                cache_keys = [
                    f"request:{event.request_id}",
                    f"request:{event.request_id}:status",
                ]

                for key in cache_keys:
                    await self._cache.delete(key)

                logger.debug(
                    "cache_invalidated",
                    extra={
                        "request_id": event.request_id,
                        "keys_invalidated": len(cache_keys),
                    },
                )

            except Exception as e:
                logger.warning(
                    "cache_invalidation_failed",
                    extra={
                        "request_id": event.request_id,
                        "error": str(e),
                    },
                )


class WebhookEventHandler:
    """Event handler for sending webhooks to external systems.

    This handler responds to domain events and sends HTTP webhooks to
    configured external endpoints for integration purposes.
    """

    def __init__(self, webhook_client: Any | None = None, webhook_url: str | None = None) -> None:
        """Initialize the handler.

        Args:
            webhook_client: Optional HTTP client for sending webhooks.
            webhook_url: Optional webhook URL to send events to.

        """
        self._webhook_client = webhook_client
        self._webhook_url = webhook_url

    async def on_summary_created(self, event: SummaryCreated) -> None:
        """Send webhook when a new summary is created.

        Args:
            event: SummaryCreated domain event.

        """
        logger.debug(
            "sending_summary_created_webhook",
            extra={
                "summary_id": event.summary_id,
                "request_id": event.request_id,
            },
        )

        if self._webhook_client and self._webhook_url:
            try:
                payload = {
                    "event_type": "summary.created",
                    "event_id": f"{event.aggregate_id}_{event.occurred_at.isoformat()}",
                    "timestamp": event.occurred_at.isoformat(),
                    "data": {
                        "summary_id": event.summary_id,
                        "request_id": event.request_id,
                        "language": event.language,
                        "has_insights": event.has_insights,
                    },
                }

                await self._webhook_client.post(
                    self._webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                logger.info(
                    "webhook_sent",
                    extra={
                        "event_type": "summary.created",
                        "summary_id": event.summary_id,
                        "webhook_url": self._webhook_url,
                    },
                )

            except Exception as e:
                logger.warning(
                    "webhook_send_failed",
                    extra={
                        "event_type": "summary.created",
                        "summary_id": event.summary_id,
                        "error": str(e),
                    },
                )

    async def on_request_completed(self, event: RequestCompleted) -> None:
        """Send webhook when a request is completed.

        Args:
            event: RequestCompleted domain event.

        """
        logger.debug(
            "sending_request_completed_webhook",
            extra={
                "request_id": event.request_id,
                "summary_id": event.summary_id,
            },
        )

        if self._webhook_client and self._webhook_url:
            try:
                payload = {
                    "event_type": "request.completed",
                    "event_id": f"{event.aggregate_id}_{event.occurred_at.isoformat()}",
                    "timestamp": event.occurred_at.isoformat(),
                    "data": {
                        "request_id": event.request_id,
                        "summary_id": event.summary_id,
                    },
                }

                await self._webhook_client.post(
                    self._webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                logger.info(
                    "webhook_sent",
                    extra={
                        "event_type": "request.completed",
                        "request_id": event.request_id,
                        "webhook_url": self._webhook_url,
                    },
                )

            except Exception as e:
                logger.warning(
                    "webhook_send_failed",
                    extra={
                        "event_type": "request.completed",
                        "request_id": event.request_id,
                        "error": str(e),
                    },
                )

    async def on_request_failed(self, event: RequestFailed) -> None:
        """Send webhook when a request fails.

        Args:
            event: RequestFailed domain event.

        """
        logger.debug(
            "sending_request_failed_webhook",
            extra={
                "request_id": event.request_id,
                "error_message": event.error_message,
            },
        )

        if self._webhook_client and self._webhook_url:
            try:
                payload = {
                    "event_type": "request.failed",
                    "event_id": f"{event.aggregate_id}_{event.occurred_at.isoformat()}",
                    "timestamp": event.occurred_at.isoformat(),
                    "data": {
                        "request_id": event.request_id,
                        "error_message": event.error_message,
                        "error_details": event.error_details,
                    },
                }

                await self._webhook_client.post(
                    self._webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                logger.info(
                    "webhook_sent",
                    extra={
                        "event_type": "request.failed",
                        "request_id": event.request_id,
                        "webhook_url": self._webhook_url,
                    },
                )

            except Exception as e:
                logger.warning(
                    "webhook_send_failed",
                    extra={
                        "event_type": "request.failed",
                        "request_id": event.request_id,
                        "error": str(e),
                    },
                )


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
    """Wire up all event handlers to the event bus.

    This function subscribes all event handlers to their respective events.
    Call this during application initialization.

    Args:
        event_bus: The EventBus instance.
        database: Database instance for handlers that need it.
        analytics_service: Optional analytics service client.
        telegram_client: Optional Telegram client for notifications.
        notification_service: Optional notification service for other channels.
        cache_service: Optional cache service (Redis, Memcached, etc.).
        webhook_client: Optional HTTP client for sending webhooks.
        webhook_url: Optional webhook URL to send events to.
        embedding_generator: Optional SummaryEmbeddingGenerator for vector embeddings.
        vector_store: Optional ChromaVectorStore for note embeddings.
        summary_repository: Optional repository for summary operations.

    Example:
        ```python
        from app.infrastructure.messaging.event_bus import EventBus
        from app.infrastructure.messaging.event_handlers import wire_event_handlers

        event_bus = EventBus()
        wire_event_handlers(
            event_bus,
            database,
            analytics_service=analytics,
            cache_service=redis_client,
            webhook_url="https://example.com/webhooks",
            embedding_generator=embedding_gen,
            summary_repository=summary_repo,
        )

        # Now when events are published, all handlers are called
        await event_bus.publish(SummaryCreated(...))
        ```

    """
    # Create core handler instances (always enabled)
    search_index_handler = SearchIndexEventHandler(database)
    analytics_handler = AnalyticsEventHandler(analytics_service)
    audit_log_handler = AuditLogEventHandler(database)

    # Create optional handler instances (only if services provided)
    notification_handler = NotificationEventHandler(telegram_client, notification_service)
    cache_handler = CacheInvalidationEventHandler(cache_service)
    webhook_handler = WebhookEventHandler(webhook_client, webhook_url)
    embedding_handler = (
        EmbeddingGenerationEventHandler(embedding_generator, summary_repository, vector_store)
        if embedding_generator and summary_repository
        else None
    )

    # Wire up summary events
    event_bus.subscribe(SummaryCreated, search_index_handler.on_summary_created)
    event_bus.subscribe(SummaryCreated, audit_log_handler.on_summary_created)
    event_bus.subscribe(SummaryCreated, cache_handler.on_summary_created)
    event_bus.subscribe(SummaryCreated, webhook_handler.on_summary_created)
    if embedding_handler:
        event_bus.subscribe(SummaryCreated, embedding_handler.on_summary_created)

    event_bus.subscribe(SummaryMarkedAsRead, search_index_handler.on_summary_marked_as_read)
    event_bus.subscribe(SummaryMarkedAsRead, analytics_handler.on_summary_marked_as_read)
    event_bus.subscribe(SummaryMarkedAsRead, cache_handler.on_summary_marked_as_read)

    # Wire up request events
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
