"""Application services for topic-based article discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.application.dto.topic_search import TopicArticle
from app.application.services.topic_search_utils import clean_snippet, tokenize
from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from app.adapters.external.firecrawl.client import FirecrawlClient
    from app.adapters.external.firecrawl.models import FirecrawlSearchItem
    from app.application.ports import TopicSearchRepositoryPort

logger = get_logger(__name__)

__all__ = ["LocalTopicSearchService", "TopicArticle", "TopicSearchService"]


class TopicSearchService:
    """Facade that wraps Firecrawl search for topic-based article discovery."""

    def __init__(
        self,
        firecrawl: FirecrawlClient,
        *,
        max_results: int,
        audit_func: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> None:
        if max_results <= 0:
            msg = "max_results must be positive"
            raise ValueError(msg)
        if max_results > 10:
            msg = "max_results must be 10 or fewer"
            raise ValueError(msg)

        self._firecrawl = firecrawl
        self._max_results = max_results
        self._audit = audit_func

    async def find_articles(
        self, topic: str, *, correlation_id: str | None = None
    ) -> list[TopicArticle]:
        """Return a curated list of articles for the provided topic."""
        query = (topic or "").strip()
        if not query:
            msg = "Topic query must not be empty"
            raise ValueError(msg)

        try:
            result = await self._firecrawl.search(query, limit=self._max_results)
        except (OSError, TimeoutError, RuntimeError):
            logger.exception(
                "topic_search_request_failed", extra={"cid": correlation_id, "topic": query}
            )
            raise

        if result.status != "success":
            message = result.error_text or "Search request failed"
            if self._audit:
                try:
                    self._audit(
                        "ERROR",
                        "topic_search_failed",
                        {
                            "topic": query,
                            "cid": correlation_id,
                            "status": result.status,
                            "http_status": result.http_status,
                            "error": message,
                        },
                    )
                except (RuntimeError, ValueError, TypeError):
                    logger.debug("topic_search_audit_failed", exc_info=True)
            raise RuntimeError(message)

        articles = self._normalize_articles(result.results)

        if self._audit:
            try:
                self._audit(
                    "INFO",
                    "topic_search_completed",
                    {
                        "topic": query,
                        "cid": correlation_id,
                        "results": len(articles),
                        "total_results": result.total_results,
                    },
                )
            except (RuntimeError, ValueError, TypeError):
                logger.debug("topic_search_completion_audit_failed", exc_info=True)

        return articles

    def _normalize_articles(self, raw_items: Iterable[FirecrawlSearchItem]) -> list[TopicArticle]:
        """Normalize Firecrawl search items into ``TopicArticle`` objects."""
        articles: list[TopicArticle] = []
        seen_urls: set[str] = set()
        for item in raw_items:
            if not item.url or item.url in seen_urls:
                continue
            seen_urls.add(item.url)

            title = item.title.strip() if item.title else item.url
            snippet = clean_snippet(item.snippet)
            source = item.source.strip() if item.source else None
            published = item.published_at.strip() if item.published_at else None

            articles.append(
                TopicArticle(
                    title=title,
                    url=item.url,
                    snippet=snippet,
                    source=source,
                    published_at=published,
                )
            )

            if len(articles) >= self._max_results:
                break

        return articles


class LocalTopicSearchService:
    """Search service that queries stored summaries via the application port."""

    def __init__(
        self,
        repository: TopicSearchRepositoryPort,
        *,
        max_results: int,
        audit_func: Callable[[str, str, dict[str, Any]], None] | None = None,
        max_scan: int | None = None,
    ) -> None:
        if max_results <= 0:
            msg = "max_results must be positive"
            raise ValueError(msg)
        if max_results > 25:
            msg = "max_results must be 25 or fewer"
            raise ValueError(msg)

        self._repo = repository
        self._max_results = max_results
        self._max_scan = (
            max(200, max_results * 40) if max_scan is None else max(max_scan, max_results)
        )
        self._audit = audit_func

    async def find_articles(
        self, topic: str, *, correlation_id: str | None = None
    ) -> list[TopicArticle]:
        """Return locally stored articles that match the requested topic."""
        query = (topic or "").strip()
        if not query:
            msg = "Topic query must not be empty"
            raise ValueError(msg)

        try:
            articles = await self._search_async(query)
        except (RuntimeError, ValueError, OSError):
            logger.exception(
                "local_topic_search_failed", extra={"cid": correlation_id, "topic": query}
            )
            raise

        if self._audit:
            try:
                self._audit(
                    "INFO",
                    "local_topic_search_completed",
                    {
                        "topic": query,
                        "cid": correlation_id,
                        "results": len(articles),
                    },
                )
            except (RuntimeError, ValueError, TypeError):
                logger.debug("local_topic_search_completion_audit_failed", exc_info=True)

        return articles

    async def _search_async(self, query: str) -> list[TopicArticle]:
        terms = tokenize(query)
        normalized_query = query.casefold()

        docs = await self._repo.async_search_documents(query, limit=self._max_results)
        articles = [self._doc_to_article(doc) for doc in docs]

        if len(articles) >= self._max_results:
            return articles[: self._max_results]

        remaining = self._max_results - len(articles)
        seen_urls = {article.url for article in articles}
        fallback_docs = await self._repo.async_scan_documents(
            terms=terms,
            normalized_query=normalized_query,
            seen_urls=seen_urls,
            limit=remaining,
            max_scan=self._max_scan,
        )

        articles.extend(self._doc_to_article(doc) for doc in fallback_docs)
        return articles[: self._max_results]

    def _doc_to_article(self, doc: Any) -> TopicArticle:
        return TopicArticle(
            title=doc.title,
            url=doc.url,
            snippet=doc.snippet,
            source=doc.source,
            published_at=doc.published_at,
        )
