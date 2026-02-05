"""Search index event handler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.infrastructure.persistence.sqlite.repositories.topic_search_repository import (
    SqliteTopicSearchRepositoryAdapter,
)

if TYPE_CHECKING:
    from app.domain.events.summary_events import SummaryCreated, SummaryMarkedAsRead

logger = logging.getLogger(__name__)


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

    async def on_summary_marked_as_read(self, event: SummaryMarkedAsRead) -> None:
        logger.debug("summary_marked_as_read_event", extra={"summary_id": event.summary_id})
