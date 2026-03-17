"""Backward-compat re-export — real implementation in app/application/services/topic_search."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.application.services.topic_search import (
    LocalTopicSearchService as _CanonicalLocal,
    TopicArticle,
    TopicSearchService,
)
from app.infrastructure.persistence.sqlite.repositories.topic_search_repository import (
    SqliteTopicSearchRepositoryAdapter,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.db.session import DatabaseSessionManager


class LocalTopicSearchService(_CanonicalLocal):
    """Backward-compat wrapper that accepts a DatabaseSessionManager instead of a port."""

    def __init__(
        self,
        db: DatabaseSessionManager | Any,
        *,
        max_results: int,
        audit_func: Callable[[str, str, dict[str, Any]], None] | None = None,
        max_scan: int | None = None,
    ) -> None:
        if isinstance(db, SqliteTopicSearchRepositoryAdapter):
            repo = db
        else:
            repo = SqliteTopicSearchRepositoryAdapter(db)
        super().__init__(
            repository=repo,
            max_results=max_results,
            audit_func=audit_func,
            max_scan=max_scan,
        )


__all__ = ["LocalTopicSearchService", "TopicArticle", "TopicSearchService"]
