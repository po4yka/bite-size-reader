"""Application-layer ports for use case dependencies.

Use cases should depend on these Protocol contracts rather than concrete
infrastructure adapters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from datetime import datetime

    from app.domain.models.summary import Summary as DomainSummary


class SummaryRepositoryPort(Protocol):
    """Port for summary query/update operations used in application use cases."""

    async def async_get_user_summaries(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        is_read: bool | None = None,
        is_favorited: bool | None = None,
        lang: str | None = None,
        start_date: Any | None = None,
        end_date: Any | None = None,
        sort: str = "created_at_desc",
    ) -> tuple[list[dict[str, Any]], int, int]:
        """Return user summaries with pagination metadata."""

    async def async_get_user_summaries_for_insights(
        self,
        user_id: int,
        request_created_after: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return summary rows used for insights/statistics."""

    async def async_get_unread_summaries(
        self,
        uid: int | None,
        cid: int | None,
        limit: int = 10,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return unread summaries for user/chat."""

    async def async_get_summary_by_id(self, summary_id: int) -> dict[str, Any] | None:
        """Return summary by ID."""

    async def async_get_summary_context_by_id(self, summary_id: int) -> dict[str, Any] | None:
        """Return summary joined with its request and crawl result."""

    async def async_get_summary_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Return summary by request ID."""

    async def async_get_summary_id_by_request(self, request_id: int) -> int | None:
        """Return summary ID by request ID."""

    async def async_get_summaries_by_request_ids(
        self, request_ids: list[int]
    ) -> dict[int, dict[str, Any]]:
        """Return summaries mapped by request ID."""

    async def async_mark_summary_as_read(self, summary_id: int) -> None:
        """Mark summary as read."""

    async def async_mark_summary_as_unread(self, summary_id: int) -> None:
        """Mark summary as unread."""

    async def async_soft_delete_summary(self, summary_id: int) -> None:
        """Soft-delete summary."""

    async def async_toggle_favorite(self, summary_id: int) -> bool:
        """Toggle favorite status and return the new state."""

    def to_domain_model(self, db_summary: dict[str, Any]) -> DomainSummary:
        """Convert persistence dictionary into a domain model."""


class RequestRepositoryPort(Protocol):
    """Port for request read operations used in application use cases."""

    async def async_get_request_id_by_url_with_summary(self, user_id: int, url: str) -> int | None:
        """Return request ID for URL owned by user that has a summary."""

    async def async_get_request_by_id(self, request_id: int) -> dict[str, Any] | None:
        """Return request by ID."""

    async def async_get_request_context(self, request_id: int) -> dict[str, Any] | None:
        """Return request joined with its crawl result and summary."""

    async def async_get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict[str, Any] | None:
        """Return request by dedupe hash."""

    async def async_get_requests_by_ids(
        self, request_ids: list[int], user_id: int | None = None
    ) -> dict[int, dict[str, Any]]:
        """Return requests mapped by ID."""


class CrawlResultRepositoryPort(Protocol):
    """Port for crawl-result query operations."""

    async def async_get_crawl_result_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Return crawl result by request ID."""


class LLMRepositoryPort(Protocol):
    """Port for LLM-call query operations."""

    async def async_get_llm_calls_by_request(self, request_id: int) -> list[dict[str, Any]]:
        """Return LLM calls by request ID."""

    async def async_count_llm_calls_by_request(self, request_id: int) -> int:
        """Return the number of LLM calls by request ID."""


class TopicSearchRepositoryPort(Protocol):
    """Port for topic search query operations."""

    async def async_fts_search_paginated(
        self, query: str, *, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        """Execute paginated FTS query."""
