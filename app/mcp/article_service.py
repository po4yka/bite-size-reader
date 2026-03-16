from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.mcp.helpers import (
    ensure_mapping,
    format_summary_compact,
    format_summary_detail,
    isotime,
    paginated_payload,
)

logger = logging.getLogger("bsr.mcp")

if TYPE_CHECKING:
    from app.mcp.context import McpServerContext


class ArticleReadService:
    def __init__(self, context: McpServerContext) -> None:
        self.context = context

    def search_articles(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Search stored article summaries by keyword, topic, or entity."""
        from app.db.models import Request, Summary, TopicSearchIndex

        limit = max(1, min(25, limit))

        try:
            fts_results = (
                TopicSearchIndex.search(query)
                .select(TopicSearchIndex.request_id, TopicSearchIndex.rank())
                .limit(limit)
                .dicts()
            )
            fts_list = list(fts_results)

            if not fts_list:
                return self._fallback_search(query, limit)

            ranked_request_ids: list[int] = []
            seen_request_ids: set[int] = set()
            for row in fts_list:
                raw_request_id = row.get("request_id")
                if raw_request_id in (None, ""):
                    continue
                try:
                    request_id = int(raw_request_id)
                except (TypeError, ValueError) as exc:
                    logger.debug(
                        "mcp_fts_invalid_request_id",
                        extra={"request_id": str(raw_request_id), "error": str(exc)},
                    )
                    continue
                if request_id in seen_request_ids:
                    continue
                seen_request_ids.add(request_id)
                ranked_request_ids.append(request_id)

            if not ranked_request_ids:
                return {"results": [], "total": 0, "query": query}

            rank_position = {request_id: idx for idx, request_id in enumerate(ranked_request_ids)}

            summaries = (
                Summary.select(Summary, Request)
                .join(Request)
                .where(
                    Request.id.in_(ranked_request_ids),
                    Summary.is_deleted == False,  # noqa: E712
                    *self.context.request_scope_filters(Request),
                )
            )

            by_request_id: dict[int, dict[str, Any]] = {}
            for summary in summaries:
                request = summary.request
                request_id = int(request.id)
                if request_id not in by_request_id:
                    by_request_id[request_id] = format_summary_compact(summary, request)

            ordered_request_ids = sorted(
                by_request_id.keys(),
                key=lambda request_id: rank_position.get(request_id, len(rank_position)),
            )
            results = [by_request_id[request_id] for request_id in ordered_request_ids][:limit]
            return {"results": results, "total": len(results), "query": query}
        except Exception as exc:
            logger.exception("search_articles failed")
            return {"error": str(exc), "query": query}

    def _fallback_search(self, query: str, limit: int) -> dict[str, Any]:
        from app.db.models import Request, Summary

        query_lower = query.lower()
        terms = query_lower.split()

        all_summaries = (
            Summary.select(Summary, Request)
            .join(Request)
            .where(
                Summary.is_deleted == False,  # noqa: E712
                *self.context.request_scope_filters(Request),
            )
            .order_by(Summary.created_at.desc())
            .limit(200)
        )

        results = []
        for summary in all_summaries:
            payload = ensure_mapping(getattr(summary, "json_payload", None))
            searchable = " ".join(
                [
                    str(payload.get("summary_250", "")),
                    str(payload.get("tldr", "")),
                    " ".join(payload.get("topic_tags", [])),
                    " ".join(payload.get("seo_keywords", [])),
                    str(ensure_mapping(payload.get("metadata")).get("title", "")),
                ]
            ).lower()
            if any(term in searchable for term in terms):
                results.append(format_summary_compact(summary, summary.request))
                if len(results) >= limit:
                    break

        return {"results": results, "total": len(results), "query": query}

    def get_article(self, summary_id: int) -> dict[str, Any]:
        from app.db.models import Request, Summary

        try:
            summary = (
                Summary.select(Summary, Request)
                .join(Request)
                .where(
                    Summary.id == summary_id,
                    Summary.is_deleted == False,  # noqa: E712
                    *self.context.request_scope_filters(Request),
                )
                .get()
            )
            return format_summary_detail(summary, summary.request)
        except Summary.DoesNotExist:
            return {"error": f"Summary {summary_id} not found"}
        except Exception as exc:
            logger.exception("get_article failed")
            return {"error": str(exc)}

    def list_articles(
        self,
        limit: int = 20,
        offset: int = 0,
        is_favorited: bool | None = None,
        lang: str | None = None,
        tag: str | None = None,
    ) -> dict[str, Any]:
        from app.db.models import Request, Summary

        limit = max(1, min(100, limit))
        offset = max(0, offset)

        try:
            query = (
                Summary.select(Summary, Request)
                .join(Request)
                .where(
                    Summary.is_deleted == False,  # noqa: E712
                    *self.context.request_scope_filters(Request),
                )
            )

            if is_favorited is not None:
                query = query.where(Summary.is_favorited == is_favorited)
            if lang:
                query = query.where(Summary.lang == lang)

            ordered_query = query.order_by(Summary.created_at.desc())

            if tag:
                tag_normalized = tag if tag.startswith("#") else f"#{tag}"
                tag_lower = tag_normalized.lower()
                matched_articles: list[dict[str, Any]] = []
                for summary in ordered_query:
                    compact = format_summary_compact(summary, summary.request)
                    tags = compact.get("topic_tags", [])
                    if tag_lower in [str(item).lower() for item in tags]:
                        matched_articles.append(compact)

                total = len(matched_articles)
                results = matched_articles[offset : offset + limit]
            else:
                total = query.count()
                articles = ordered_query.offset(offset).limit(limit)
                results = [format_summary_compact(summary, summary.request) for summary in articles]

            payload = paginated_payload(results=results, total=total, limit=limit, offset=offset)
            payload["has_more"] = (offset + len(results)) < total
            payload["articles"] = results
            return payload
        except Exception as exc:
            logger.exception("list_articles failed")
            return {"error": str(exc)}

    def get_article_content(self, summary_id: int) -> dict[str, Any]:
        from app.db.models import CrawlResult, Request, Summary

        try:
            summary = (
                Summary.select(Summary, Request)
                .join(Request)
                .where(
                    Summary.id == summary_id,
                    Summary.is_deleted == False,  # noqa: E712
                    *self.context.request_scope_filters(Request),
                )
                .get()
            )

            request = summary.request
            crawl = (
                CrawlResult.select()
                .where(
                    CrawlResult.request == request.id,
                    CrawlResult.is_deleted == False,  # noqa: E712
                )
                .first()
            )
            if not crawl:
                return {"error": f"No crawl content found for summary {summary_id}"}

            content = crawl.content_markdown or crawl.content_html or request.content_text or ""
            metadata = ensure_mapping(crawl.metadata_json)
            return {
                "summary_id": summary_id,
                "url": getattr(request, "input_url", ""),
                "title": metadata.get("title", "Untitled"),
                "content_format": "markdown" if crawl.content_markdown else "text",
                "content": content[:50000],
                "content_length": len(content),
                "truncated": len(content) > 50000,
            }
        except Summary.DoesNotExist:
            return {"error": f"Summary {summary_id} not found"}
        except Exception as exc:
            logger.exception("get_article_content failed")
            return {"error": str(exc)}

    def get_stats(self) -> dict[str, Any]:
        from app.db.models import Request, Summary

        try:
            scoped_summaries = (
                Summary.select(Summary, Request)
                .join(Request)
                .where(
                    Summary.is_deleted == False,  # noqa: E712
                    *self.context.request_scope_filters(Request),
                )
            )

            total = scoped_summaries.count()
            unread = scoped_summaries.where(Summary.is_read == False).count()  # noqa: E712
            favorited = scoped_summaries.where(Summary.is_favorited == True).count()  # noqa: E712

            lang_counts: dict[str, int] = {}
            for row in scoped_summaries.select(Summary.lang).dicts():
                lang = row.get("lang") or "unknown"
                lang_counts[lang] = lang_counts.get(lang, 0) + 1

            tag_counts: dict[str, int] = {}
            recent = (
                scoped_summaries.select(Summary.json_payload)
                .order_by(Summary.created_at.desc())
                .limit(200)
            )
            for row in recent:
                payload = ensure_mapping(getattr(row, "json_payload", None))
                for tag in payload.get("topic_tags", []):
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

            top_tags = sorted(tag_counts.items(), key=lambda item: item[1], reverse=True)[:20]
            url_count = (
                Request.select()
                .where(*self.context.request_scope_filters(Request), Request.type == "url")
                .count()
            )
            forward_count = (
                Request.select()
                .where(*self.context.request_scope_filters(Request), Request.type == "forward")
                .count()
            )
            return {
                "total_articles": total,
                "unread": unread,
                "favorited": favorited,
                "languages": lang_counts,
                "top_tags": [{"tag": tag, "count": count} for tag, count in top_tags],
                "request_types": {"url": url_count, "forward": forward_count},
            }
        except Exception as exc:
            logger.exception("get_stats failed")
            return {"error": str(exc)}

    def find_by_entity(
        self,
        entity_name: str,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        from app.db.models import Request, Summary

        limit = max(1, min(25, limit))
        name_lower = entity_name.lower()

        try:
            all_summaries = (
                Summary.select(Summary, Request)
                .join(Request)
                .where(
                    Summary.is_deleted == False,  # noqa: E712
                    *self.context.request_scope_filters(Request),
                )
                .order_by(Summary.created_at.desc())
                .limit(500)
            )

            results = []
            for summary in all_summaries:
                payload = ensure_mapping(getattr(summary, "json_payload", None))
                entities = ensure_mapping(payload.get("entities"))
                types_to_check = (
                    [entity_type]
                    if entity_type in ("people", "organizations", "locations")
                    else ["people", "organizations", "locations"]
                )

                matched = False
                for entity_kind in types_to_check:
                    for item in entities.get(entity_kind, []):
                        if name_lower in str(item).lower():
                            matched = True
                            break
                    if matched:
                        break

                if matched:
                    results.append(format_summary_compact(summary, summary.request))
                    if len(results) >= limit:
                        break

            return {
                "results": results,
                "total": len(results),
                "entity": entity_name,
                "entity_type": entity_type,
            }
        except Exception as exc:
            logger.exception("find_by_entity failed")
            return {"error": str(exc)}

    def check_url(self, url: str) -> dict[str, Any]:
        from app.core.url_utils import compute_dedupe_hash, normalize_url
        from app.db.models import Request, Summary

        try:
            normalized = normalize_url(url)
            dedupe_hash = compute_dedupe_hash(url)
            request = Request.get_or_none(
                Request.dedupe_hash == dedupe_hash,
                *self.context.request_scope_filters(Request),
            )
            if not request:
                return {
                    "exists": False,
                    "normalized_url": normalized,
                    "dedupe_hash": dedupe_hash,
                    "message": "URL has not been processed yet",
                }

            summary = (
                Summary.select()
                .where(
                    Summary.request == request.id,
                    Summary.is_deleted == False,  # noqa: E712
                )
                .first()
            )

            result: dict[str, Any] = {
                "exists": True,
                "normalized_url": normalized,
                "dedupe_hash": dedupe_hash,
                "request_id": request.id,
                "request_status": request.status,
                "request_type": request.type,
                "created_at": isotime(request.created_at),
            }

            if summary:
                result["summary_id"] = summary.id
                result["summary"] = format_summary_compact(summary, request)
            else:
                result["summary_id"] = None
                result["message"] = "URL was processed but no summary is available"
            return result
        except Exception as exc:
            logger.exception("check_url failed")
            return {"error": str(exc), "url": url}

    def unread_articles(self, limit: int = 20) -> dict[str, Any]:
        from app.db.models import Request, Summary

        try:
            summaries = (
                Summary.select(Summary, Request)
                .join(Request)
                .where(
                    Summary.is_deleted == False,  # noqa: E712
                    Summary.is_read == False,  # noqa: E712
                    *self.context.request_scope_filters(Request),
                )
                .order_by(Summary.created_at.desc())
                .limit(limit)
            )
            results = [format_summary_compact(summary, summary.request) for summary in summaries]
            return {"articles": results, "total": len(results)}
        except Exception as exc:
            logger.exception("unread_resource failed")
            return {"error": str(exc)}

    def tag_counts(self) -> dict[str, Any]:
        from app.db.models import Request, Summary

        try:
            counts: dict[str, int] = {}
            all_summaries = (
                Summary.select(Summary.json_payload, Request)
                .join(Request)
                .where(
                    Summary.is_deleted == False,  # noqa: E712
                    *self.context.request_scope_filters(Request),
                )
                .order_by(Summary.created_at.desc())
            )
            for row in all_summaries:
                payload = ensure_mapping(getattr(row, "json_payload", None))
                for tag in payload.get("topic_tags", []):
                    counts[tag] = counts.get(tag, 0) + 1

            sorted_tags = sorted(counts.items(), key=lambda item: item[1], reverse=True)
            return {
                "tags": [{"tag": tag, "count": count} for tag, count in sorted_tags],
                "total_unique_tags": len(sorted_tags),
            }
        except Exception as exc:
            logger.exception("tags_resource failed")
            return {"error": str(exc)}

    def entity_counts(self) -> dict[str, Any]:
        from app.db.models import Request, Summary

        try:
            people: dict[str, int] = {}
            organizations: dict[str, int] = {}
            locations: dict[str, int] = {}

            all_summaries = (
                Summary.select(Summary.json_payload, Request)
                .join(Request)
                .where(
                    Summary.is_deleted == False,  # noqa: E712
                    *self.context.request_scope_filters(Request),
                )
                .order_by(Summary.created_at.desc())
            )
            for row in all_summaries:
                payload = ensure_mapping(getattr(row, "json_payload", None))
                entities = ensure_mapping(payload.get("entities"))
                for item in entities.get("people", []):
                    people[item] = people.get(item, 0) + 1
                for item in entities.get("organizations", []):
                    organizations[item] = organizations.get(item, 0) + 1
                for item in entities.get("locations", []):
                    locations[item] = locations.get(item, 0) + 1

            def _top(items: dict[str, int], limit: int = 50) -> list[dict[str, Any]]:
                return [
                    {"name": name, "count": count}
                    for name, count in sorted(
                        items.items(), key=lambda item: item[1], reverse=True
                    )[:limit]
                ]

            return {
                "people": _top(people),
                "organizations": _top(organizations),
                "locations": _top(locations),
            }
        except Exception as exc:
            logger.exception("entities_resource failed")
            return {"error": str(exc)}

    def domain_counts(self) -> dict[str, Any]:
        from app.db.models import Request, Summary

        try:
            counts: dict[str, int] = {}
            all_summaries = (
                Summary.select(Summary.json_payload, Request)
                .join(Request)
                .where(
                    Summary.is_deleted == False,  # noqa: E712
                    *self.context.request_scope_filters(Request),
                )
            )
            for row in all_summaries:
                payload = ensure_mapping(getattr(row, "json_payload", None))
                metadata = ensure_mapping(payload.get("metadata"))
                domain = metadata.get("domain", "")
                if domain:
                    counts[domain] = counts.get(domain, 0) + 1

            sorted_domains = sorted(counts.items(), key=lambda item: item[1], reverse=True)
            return {
                "domains": [{"domain": domain, "count": count} for domain, count in sorted_domains],
                "total_unique_domains": len(sorted_domains),
            }
        except Exception as exc:
            logger.exception("domains_resource failed")
            return {"error": str(exc)}
