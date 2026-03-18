from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.mcp.helpers import format_summary_compact, isotime, paginated_payload

logger = logging.getLogger("bsr.mcp")

if TYPE_CHECKING:
    from app.mcp.context import McpServerContext


class CatalogReadService:
    def __init__(self, context: McpServerContext) -> None:
        self.context = context

    def list_collections(self, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        from app.db.models import Collection, CollectionItem

        limit = max(1, min(50, limit))
        offset = max(0, offset)

        try:
            query = Collection.select().where(
                Collection.parent.is_null(True),
                *self.context.collection_scope_filters(Collection),
            )
            total = query.count()
            collections = (
                query.order_by(Collection.position, Collection.created_at.desc())
                .offset(offset)
                .limit(limit)
            )

            results = []
            for collection in collections:
                item_count = (
                    CollectionItem.select()
                    .where(CollectionItem.collection == collection.id)
                    .count()
                )
                child_count = (
                    Collection.select()
                    .where(
                        Collection.parent == collection.id,
                        *self.context.collection_scope_filters(Collection),
                    )
                    .count()
                )
                results.append(
                    {
                        "collection_id": collection.id,
                        "name": collection.name,
                        "description": collection.description,
                        "item_count": item_count,
                        "child_collections": child_count,
                        "is_shared": collection.is_shared,
                        "created_at": isotime(collection.created_at),
                        "updated_at": isotime(collection.updated_at),
                    }
                )

            return paginated_payload(results=results, total=total, limit=limit, offset=offset)
        except Exception as exc:
            logger.exception("list_collections failed")
            return {"error": str(exc)}

    def get_collection(
        self,
        collection_id: int,
        include_items: bool = True,
        limit: int = 50,
    ) -> dict[str, Any]:
        from app.db.models import Collection, CollectionItem, Request, Summary

        limit = max(1, min(100, limit))

        try:
            collection = Collection.get_or_none(
                Collection.id == collection_id,
                *self.context.collection_scope_filters(Collection),
            )
            if not collection:
                return {"error": f"Collection {collection_id} not found"}

            children = (
                Collection.select()
                .where(
                    Collection.parent == collection.id,
                    *self.context.collection_scope_filters(Collection),
                )
                .order_by(Collection.position, Collection.created_at)
            )
            result: dict[str, Any] = {
                "collection_id": collection.id,
                "name": collection.name,
                "description": collection.description,
                "is_shared": collection.is_shared,
                "child_collections": [
                    {
                        "collection_id": child.id,
                        "name": child.name,
                        "description": child.description,
                    }
                    for child in children
                ],
                "created_at": isotime(collection.created_at),
                "updated_at": isotime(collection.updated_at),
            }

            if include_items:
                items = (
                    CollectionItem.select(CollectionItem, Summary, Request)
                    .join(Summary)
                    .join(Request)
                    .where(CollectionItem.collection == collection.id)
                    .where(
                        Summary.is_deleted == False,  # noqa: E712
                        *self.context.request_scope_filters(Request),
                    )
                    .order_by(CollectionItem.position, CollectionItem.created_at)
                    .limit(limit)
                )
                articles = [
                    format_summary_compact(item.summary, item.summary.request) for item in items
                ]
                result["articles"] = articles
                result["article_count"] = len(articles)

            return result
        except Exception as exc:
            logger.exception("get_collection failed")
            return {"error": str(exc)}

    def list_videos(
        self,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
    ) -> dict[str, Any]:
        from app.db.models import Request, VideoDownload

        limit = max(1, min(50, limit))
        offset = max(0, offset)

        try:
            query = (
                VideoDownload.select(VideoDownload, Request)
                .join(Request)
                .where(*self.context.request_scope_filters(Request))
            )
            if status and status in ("pending", "downloading", "completed", "error"):
                query = query.where(VideoDownload.status == status)

            total = query.count()
            videos = query.order_by(VideoDownload.created_at.desc()).offset(offset).limit(limit)
            results = []
            for video in videos:
                request = video.request
                results.append(
                    {
                        "video_id": video.video_id,
                        "request_id": request.id,
                        "url": getattr(request, "input_url", ""),
                        "title": video.title,
                        "channel": video.channel,
                        "duration_sec": video.duration_sec,
                        "duration_display": (
                            f"{video.duration_sec // 60}:{video.duration_sec % 60:02d}"
                            if video.duration_sec
                            else None
                        ),
                        "resolution": video.resolution,
                        "view_count": video.view_count,
                        "like_count": video.like_count,
                        "has_transcript": bool(video.transcript_text),
                        "transcript_source": video.transcript_source,
                        "status": video.status,
                        "upload_date": video.upload_date,
                        "created_at": isotime(video.created_at),
                    }
                )

            return paginated_payload(results=results, total=total, limit=limit, offset=offset)
        except Exception as exc:
            logger.exception("list_videos failed")
            return {"error": str(exc)}

    def get_video_transcript(self, video_id: str) -> dict[str, Any]:
        from app.db.models import Request, VideoDownload

        try:
            video = (
                VideoDownload.select(VideoDownload, Request)
                .join(Request)
                .where(
                    VideoDownload.video_id == video_id, *self.context.request_scope_filters(Request)
                )
                .first()
            )
            if not video:
                return {"error": f"Video {video_id} not found"}
            if not video.transcript_text:
                return {
                    "video_id": video_id,
                    "title": video.title,
                    "error": "No transcript available for this video",
                }

            return {
                "video_id": video_id,
                "title": video.title,
                "channel": video.channel,
                "duration_sec": video.duration_sec,
                "transcript_source": video.transcript_source,
                "subtitle_language": video.subtitle_language,
                "auto_generated": video.auto_generated,
                "transcript": video.transcript_text[:50000],
                "transcript_length": len(video.transcript_text),
                "truncated": len(video.transcript_text) > 50000,
            }
        except Exception as exc:
            logger.exception("get_video_transcript failed")
            return {"error": str(exc)}

    def processing_stats(self) -> dict[str, Any]:
        from peewee import fn

        from app.db.models import LLMCall, Request, VideoDownload

        try:
            llm_scope_filters = [
                not LLMCall.is_deleted,
                *self.context.request_scope_filters(Request),
            ]
            total_calls = LLMCall.select(LLMCall.id).join(Request).where(*llm_scope_filters).count()
            success_calls = (
                LLMCall.select(LLMCall.id)
                .join(Request)
                .where(*llm_scope_filters, LLMCall.status == "ok")
                .count()
            )
            error_calls = (
                LLMCall.select(LLMCall.id)
                .join(Request)
                .where(*llm_scope_filters, LLMCall.status == "error")
                .count()
            )

            token_stats = (
                LLMCall.select(
                    fn.SUM(LLMCall.tokens_prompt).alias("total_prompt"),
                    fn.SUM(LLMCall.tokens_completion).alias("total_completion"),
                    fn.SUM(LLMCall.cost_usd).alias("total_cost"),
                    fn.AVG(LLMCall.latency_ms).alias("avg_latency_ms"),
                )
                .join(Request)
                .where(*llm_scope_filters, LLMCall.status == "ok")
                .dicts()
                .first()
            ) or {}

            model_counts: dict[str, int] = {}
            for row in (
                LLMCall.select(LLMCall.model)
                .join(Request)
                .where(*llm_scope_filters, LLMCall.status == "ok", LLMCall.model.is_null(False))
                .dicts()
            ):
                model = row.get("model") or "unknown"
                model_counts[model] = model_counts.get(model, 0) + 1

            top_models = sorted(model_counts.items(), key=lambda item: item[1], reverse=True)[:10]
            video_base = (
                VideoDownload.select(VideoDownload.id)
                .join(Request)
                .where(*self.context.request_scope_filters(Request))
            )

            total_videos = video_base.count()
            completed_videos = video_base.where(VideoDownload.status == "completed").count()
            videos_with_transcript = video_base.where(
                VideoDownload.status == "completed",
                VideoDownload.transcript_text.is_null(False),
            ).count()

            return {
                "llm_calls": {
                    "total": total_calls,
                    "success": success_calls,
                    "errors": error_calls,
                    "success_rate": round(success_calls / total_calls * 100, 1)
                    if total_calls
                    else 0,
                },
                "token_usage": {
                    "total_prompt_tokens": token_stats.get("total_prompt"),
                    "total_completion_tokens": token_stats.get("total_completion"),
                    "total_cost_usd": (
                        round(float(token_stats["total_cost"]), 4)
                        if token_stats.get("total_cost")
                        else None
                    ),
                    "avg_latency_ms": (
                        round(float(token_stats["avg_latency_ms"]))
                        if token_stats.get("avg_latency_ms")
                        else None
                    ),
                },
                "top_models": [{"model": model, "calls": count} for model, count in top_models],
                "videos": {
                    "total": total_videos,
                    "completed": completed_videos,
                    "with_transcript": videos_with_transcript,
                },
            }
        except Exception as exc:
            logger.exception("processing_stats_resource failed")
            return {"error": str(exc)}
