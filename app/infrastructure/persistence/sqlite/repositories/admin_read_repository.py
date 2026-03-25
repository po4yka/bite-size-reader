"""SQLite read adapter for admin dashboards and audit log views."""

from __future__ import annotations

from typing import Any

from peewee import fn

from app.api.search_helpers import isotime
from app.db.models import (
    AuditLog,
    Collection,
    CrawlResult,
    ImportJob,
    LLMCall,
    Request,
    Summary,
    Tag,
    User,
)
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteAdminReadRepositoryAdapter(SqliteBaseRepository):
    """Read-side adapter for admin reporting queries."""

    async def async_list_users(self) -> dict[str, Any]:
        def _query() -> dict[str, Any]:
            users_list: list[dict[str, Any]] = []
            for user in User.select():
                uid = user.telegram_user_id
                summary_count = (
                    Summary.select()
                    .join(Request, on=(Summary.request == Request.id))
                    .where(Request.user_id == uid)
                    .count()
                )
                request_count = Request.select().where(Request.user_id == uid).count()
                tag_count = Tag.select().where(Tag.user == uid).count()
                collection_count = Collection.select().where(Collection.user == uid).count()
                users_list.append(
                    {
                        "user_id": uid,
                        "username": user.username,
                        "is_owner": user.is_owner,
                        "summary_count": summary_count,
                        "request_count": request_count,
                        "tag_count": tag_count,
                        "collection_count": collection_count,
                        "created_at": isotime(user.created_at),
                    }
                )
            return {"users": users_list, "total_users": len(users_list)}

        return await self._execute(_query, operation_name="admin_list_users", read_only=True)

    async def async_job_status(self, *, today: Any) -> dict[str, Any]:
        def _query() -> dict[str, Any]:
            pending = Request.select().where(Request.status == "pending").count()
            processing = (
                Request.select()
                .where(Request.status.in_(["crawling", "summarizing", "processing"]))
                .count()
            )
            completed_today = (
                Request.select()
                .where((Request.status == "completed") & (Request.updated_at >= today))
                .count()
            )
            failed_today = (
                Request.select()
                .where((Request.status == "error") & (Request.updated_at >= today))
                .count()
            )
            imports_active = ImportJob.select().where(ImportJob.status == "processing").count()
            imports_completed_today = (
                ImportJob.select()
                .where((ImportJob.status == "completed") & (ImportJob.updated_at >= today))
                .count()
            )
            return {
                "pipeline": {
                    "pending": pending,
                    "processing": processing,
                    "completed_today": completed_today,
                    "failed_today": failed_today,
                },
                "imports": {
                    "active": imports_active,
                    "completed_today": imports_completed_today,
                },
            }

        return await self._execute(_query, operation_name="admin_job_status", read_only=True)

    async def async_content_health(self) -> dict[str, Any]:
        def _query() -> dict[str, Any]:
            total_summaries = Summary.select().count()
            total_requests = Request.select().count()
            failed_requests = Request.select().where(Request.status == "error").count()

            failed_by_error_type: dict[str, int] = {}
            error_groups = (
                Request.select(Request.error_type, fn.COUNT(Request.id).alias("cnt"))
                .where(Request.status == "error")
                .group_by(Request.error_type)
            )
            for row in error_groups:
                key = row.error_type or "unknown"
                failed_by_error_type[key] = row.cnt

            recent_failures: list[dict[str, Any]] = []
            for request in (
                Request.select()
                .where(Request.status == "error")
                .order_by(Request.created_at.desc())
                .limit(20)
            ):
                recent_failures.append(
                    {
                        "id": request.id,
                        "url": request.input_url,
                        "error_type": request.error_type,
                        "error_message": request.error_message,
                        "created_at": isotime(request.created_at),
                    }
                )

            return {
                "total_summaries": total_summaries,
                "total_requests": total_requests,
                "failed_requests": failed_requests,
                "failed_by_error_type": failed_by_error_type,
                "recent_failures": recent_failures,
            }

        return await self._execute(_query, operation_name="admin_content_health", read_only=True)

    async def async_system_metrics(self, *, since: Any) -> dict[str, Any]:
        def _query() -> dict[str, Any]:
            llm_total = LLMCall.select().where(LLMCall.created_at >= since).count()
            llm_agg = (
                LLMCall.select(
                    fn.AVG(LLMCall.latency_ms).alias("avg_latency"),
                    fn.SUM(LLMCall.tokens_prompt).alias("total_prompt_tokens"),
                    fn.SUM(LLMCall.tokens_completion).alias("total_completion_tokens"),
                    fn.SUM(LLMCall.cost_usd).alias("total_cost"),
                )
                .where(LLMCall.created_at >= since)
                .dicts()
                .first()
            ) or {}
            llm_errors = (
                LLMCall.select()
                .where((LLMCall.created_at >= since) & (LLMCall.status == "error"))
                .count()
            )
            llm_stats = {
                "total_calls": llm_total,
                "avg_latency_ms": round(llm_agg.get("avg_latency") or 0, 1),
                "total_prompt_tokens": int(llm_agg.get("total_prompt_tokens") or 0),
                "total_completion_tokens": int(llm_agg.get("total_completion_tokens") or 0),
                "total_cost_usd": round(float(llm_agg.get("total_cost") or 0), 4),
                "error_rate": round(llm_errors / llm_total, 4) if llm_total else 0.0,
            }

            scraper_rows = (
                CrawlResult.select(
                    CrawlResult.endpoint,
                    fn.COUNT(CrawlResult.id).alias("total"),
                    fn.SUM(
                        fn.CASE(None, [(CrawlResult.firecrawl_success == True, 1)], 0)  # noqa: E712
                    ).alias("success"),
                )
                .join(Request, on=(CrawlResult.request == Request.id))
                .where(Request.created_at >= since)
                .group_by(CrawlResult.endpoint)
            )
            scraper_stats: dict[str, Any] = {}
            for row in scraper_rows:
                provider = row.endpoint or "unknown"
                total = row.total or 0
                success = row.success or 0
                scraper_stats[provider] = {
                    "total": total,
                    "success": success,
                    "success_rate": round(success / total, 4) if total else 0.0,
                }

            return {"llm_7d": llm_stats, "scraper_7d": scraper_stats}

        return await self._execute(_query, operation_name="admin_system_metrics", read_only=True)

    async def async_audit_log(
        self,
        *,
        action: str | None,
        user_id_filter: int | None,
        since: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        def _query() -> dict[str, Any]:
            query = AuditLog.select()
            if action:
                query = query.where(AuditLog.event == action)
            if since:
                query = query.where(AuditLog.ts >= since)

            total = query.count()
            logs: list[dict[str, Any]] = []
            for entry in query.order_by(AuditLog.ts.desc()).offset(offset).limit(limit):
                details = entry.details_json
                if user_id_filter is not None:
                    if not isinstance(details, dict) or details.get("user_id") != user_id_filter:
                        total -= 1
                        continue
                logs.append(
                    {
                        "id": entry.id,
                        "timestamp": isotime(entry.ts),
                        "level": entry.level,
                        "event": entry.event,
                        "details": details,
                    }
                )

            return {"logs": logs, "total": total, "limit": limit, "offset": offset}

        return await self._execute(_query, operation_name="admin_audit_log", read_only=True)
