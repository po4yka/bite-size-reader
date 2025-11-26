"""Service helpers for topic-based article discovery."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from app.db.models import Request, Summary
from app.services.topic_search_utils import (
    build_snippet,
    clean_snippet,
    compose_search_body,
    ensure_mapping,
    normalize_text,
    tokenize,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from app.adapters.external.firecrawl_parser import FirecrawlClient, FirecrawlSearchItem
    from app.db.database import Database

logger = logging.getLogger(__name__)


class TopicArticle(BaseModel):
    """Lightweight representation of a discovered article."""

    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    snippet: str | None = None
    source: str | None = None
    published_at: str | None = None


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
                except (RuntimeError, ValueError, TypeError):  # pragma: no cover - defensive audit
                    pass
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
            except (RuntimeError, ValueError, TypeError):  # pragma: no cover - defensive audit
                pass

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
    """Search service that queries stored summaries in the local database."""

    def __init__(
        self,
        db: Database,
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

        self._db = db
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
            articles = await asyncio.to_thread(self._search_sync, query)
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
            except (RuntimeError, ValueError, TypeError):  # pragma: no cover - defensive audit
                pass

        return articles

    def _search_sync(self, query: str) -> list[TopicArticle]:
        terms = tokenize(query)
        normalized_query = query.casefold()

        articles = self._search_via_index(query, terms)
        if len(articles) >= self._max_results:
            return articles[: self._max_results]

        remaining = self._max_results - len(articles)
        if remaining <= 0:
            return articles

        seen_urls = {article.url for article in articles}
        fallback_articles = self._scan_summaries(
            terms=terms,
            normalized_query=normalized_query,
            seen_urls=seen_urls,
            limit=remaining,
        )
        articles.extend(fallback_articles)
        return articles[: self._max_results]

    def _search_via_index(self, query: str, terms: Sequence[str]) -> list[TopicArticle]:
        if not terms:
            sanitized = self._sanitize_fts_term(query.casefold())
            if not sanitized:
                return []
            fts_query = f'"{sanitized}"*'
        else:
            sanitized_terms = [self._sanitize_fts_term(term) for term in terms]
            sanitized_terms = [term for term in sanitized_terms if term]
            if not sanitized_terms:
                return []
            phrase = self._sanitize_fts_term(" ".join(terms))
            wildcard_terms = [f'"{term}"*' for term in sanitized_terms]
            components = [" AND ".join(wildcard_terms)]
            if phrase:
                components.append(f'"{phrase}"')
            fts_query = " OR ".join(component for component in components if component)

        candidate_limit = max(self._max_results * 5, 25)
        sql = (
            "SELECT rowid, url, title, snippet, source, published_at "
            "FROM topic_search_index "
            "WHERE topic_search_index MATCH ? "
            "ORDER BY bm25(topic_search_index) ASC "
            "LIMIT ?"
        )

        articles: list[TopicArticle] = []
        seen_urls: set[str] = set()

        try:
            with self._db._database.connection_context():
                cursor = self._db._database.execute_sql(sql, (fts_query, candidate_limit))
                rows = list(cursor)
        except Exception as exc:
            logger.warning("local_topic_search_index_query_failed", extra={"error": str(exc)})
            return []

        for row in rows:
            url = normalize_text(self._row_value(row, 1, "url"))
            if not url or url in seen_urls:
                continue

            title = normalize_text(self._row_value(row, 2, "title")) or url
            snippet = clean_snippet(self._row_value(row, 3, "snippet"))
            source = normalize_text(self._row_value(row, 4, "source"))
            published = normalize_text(self._row_value(row, 5, "published_at"))

            articles.append(
                TopicArticle(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source=source,
                    published_at=published,
                )
            )
            seen_urls.add(url)
            if len(articles) >= self._max_results:
                break

        return articles

    def _scan_summaries(
        self,
        *,
        terms: Sequence[str],
        normalized_query: str,
        seen_urls: set[str],
        limit: int,
    ) -> list[TopicArticle]:
        if limit <= 0:
            return []

        articles: list[TopicArticle] = []

        with self._db._database.connection_context():
            query = (
                Summary.select(Summary, Request)
                .join(Request)
                .where(Summary.json_payload.is_null(False))
                .order_by(Summary.created_at.desc())
            )
            if self._max_scan:
                query = query.limit(self._max_scan)

            for row in query:
                payload = ensure_mapping(row.json_payload)
                metadata = ensure_mapping(payload.get("metadata"))

                url = (
                    normalize_text(metadata.get("canonical_url"))
                    or normalize_text(metadata.get("url"))
                    or normalize_text(getattr(row.request, "normalized_url", None))
                    or normalize_text(getattr(row.request, "input_url", None))
                )
                if not url or url in seen_urls:
                    continue

                title = (
                    normalize_text(metadata.get("title"))
                    or normalize_text(payload.get("title"))
                    or url
                )

                haystack, _ = compose_search_body(
                    title=title,
                    payload=payload,
                    metadata=metadata,
                    content_text=getattr(row.request, "content_text", None),
                )

                if not self._matches(terms, normalized_query, haystack):
                    continue

                snippet = build_snippet(payload)
                source = normalize_text(metadata.get("domain") or metadata.get("source"))
                published = normalize_text(
                    metadata.get("published_at")
                    or metadata.get("published")
                    or metadata.get("last_updated")
                )

                articles.append(
                    TopicArticle(
                        title=title,
                        url=url,
                        snippet=snippet,
                        source=source,
                        published_at=published,
                    )
                )

                seen_urls.add(url)
                if len(articles) >= limit:
                    break

        return articles

    @staticmethod
    def _matches(terms: Sequence[str], normalized_query: str, haystack: str) -> bool:
        if not haystack:
            return False
        if not terms:
            return normalized_query in haystack
        return all(term in haystack for term in terms)

    @staticmethod
    def _sanitize_fts_term(term: str) -> str:
        sanitized = re.sub(r"[^\w-]+", " ", term)
        return re.sub(r"\s+", " ", sanitized).strip()

    @staticmethod
    def _row_value(row: Any, index: int, key: str) -> Any:
        if isinstance(row, dict):
            return row.get(key)
        if hasattr(row, "keys"):
            try:
                return row[key]
            except (KeyError, TypeError, IndexError):  # pragma: no cover - defensive fallback
                pass
        try:
            return row[index]
        except (KeyError, TypeError, IndexError):  # pragma: no cover - defensive fallback
            return None
