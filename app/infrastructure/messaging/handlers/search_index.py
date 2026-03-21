"""Search index event handler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger
from app.infrastructure.persistence.sqlite.repositories.topic_search_repository import (
    SqliteTopicSearchRepositoryAdapter,
)

if TYPE_CHECKING:
    from app.domain.events.summary_events import SummaryCreated
    from app.domain.events.tag_events import TagAttached, TagDetached

logger = get_logger(__name__)


class SearchIndexEventHandler:
    """Update the full-text search index when summary data changes."""

    def __init__(self, database: Any) -> None:
        if isinstance(database, SqliteTopicSearchRepositoryAdapter):
            self._repo = database
        else:
            self._repo = SqliteTopicSearchRepositoryAdapter(database)

    async def on_summary_created(self, event: SummaryCreated) -> None:
        logger.info(
            "updating_search_index_for_new_summary",
            extra={
                "summary_id": event.summary_id,
                "request_id": event.request_id,
                "language": event.language,
            },
        )

        try:
            await self._repo.async_refresh_index(event.request_id)
            logger.debug(
                "search_index_updated",
                extra={"request_id": event.request_id, "summary_id": event.summary_id},
            )
        except Exception as exc:
            logger.exception(
                "search_index_update_failed",
                extra={
                    "summary_id": event.summary_id,
                    "request_id": event.request_id,
                    "error": str(exc),
                },
            )

    async def on_tag_attached(self, event: TagAttached) -> None:
        logger.info(
            "updating_search_index_tags_on_attach",
            extra={"summary_id": event.summary_id, "tag_id": event.tag_id},
        )
        try:
            await self._repo.async_update_tags_for_summary(event.summary_id)
            logger.debug(
                "search_index_tags_updated",
                extra={"summary_id": event.summary_id, "tag_id": event.tag_id},
            )
        except Exception as exc:
            logger.exception(
                "search_index_tag_update_failed",
                extra={
                    "summary_id": event.summary_id,
                    "tag_id": event.tag_id,
                    "error": str(exc),
                },
            )

    async def on_tag_detached(self, event: TagDetached) -> None:
        logger.info(
            "updating_search_index_tags_on_detach",
            extra={"summary_id": event.summary_id, "tag_id": event.tag_id},
        )
        try:
            await self._repo.async_update_tags_for_summary(event.summary_id)
            logger.debug(
                "search_index_tags_updated",
                extra={"summary_id": event.summary_id, "tag_id": event.tag_id},
            )
        except Exception as exc:
            logger.exception(
                "search_index_tag_update_failed",
                extra={
                    "summary_id": event.summary_id,
                    "tag_id": event.tag_id,
                    "error": str(exc),
                },
            )
