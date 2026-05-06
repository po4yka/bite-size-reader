"""MCP service for signal sources and triage queue."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

if TYPE_CHECKING:
    from app.mcp.context import McpServerContext


class SignalMcpService:
    def __init__(self, context: McpServerContext) -> None:
        self.context = context

    async def list_sources(self, limit: int = 50) -> dict[str, Any]:
        from app.db.models import Source

        runtime = self.context.ensure_runtime()
        async with runtime.database.session() as session:
            rows = (
                await session.scalars(
                    select(Source).order_by(Source.created_at.desc()).limit(max(1, min(limit, 100)))
                )
            ).all()
        return {"sources": [self._source(row) for row in rows]}

    async def list_signals(self, limit: int = 20, status: str | None = None) -> dict[str, Any]:
        from app.db.models import FeedItem, UserSignal

        query = select(UserSignal).options(
            selectinload(UserSignal.feed_item).selectinload(FeedItem.source),
            selectinload(UserSignal.topic),
        )
        if self.context.user_id is not None:
            query = query.where(UserSignal.user_id == self.context.user_id)
        if status:
            query = query.where(UserSignal.status == status)
        query = query.order_by(
            UserSignal.final_score.desc().nulls_last(),
            UserSignal.created_at.desc(),
        ).limit(max(1, min(limit, 100)))

        runtime = self.context.ensure_runtime()
        async with runtime.database.session() as session:
            rows = (await session.scalars(query)).all()
        return {"signals": [self._signal(row) for row in rows]}

    async def update_signal_feedback(self, signal_id: int, action: str) -> dict[str, Any]:
        from app.infrastructure.persistence.repositories.signal_source_repository import (
            SqliteSignalSourceRepositoryAdapter,
        )

        runtime = await self.context.ensure_api_runtime()
        repo = SqliteSignalSourceRepositoryAdapter(runtime.db)
        user_id = self.context.user_id
        if user_id is None:
            return {"error": "Signal feedback requires a scoped MCP user"}
        if action == "hide_source":
            updated = await repo.async_hide_signal_source(user_id=user_id, signal_id=signal_id)
        elif action == "boost_topic":
            updated = await repo.async_boost_signal_topic(user_id=user_id, signal_id=signal_id)
        else:
            status = {
                "like": "liked",
                "dislike": "dismissed",
                "skip": "skipped",
                "queue": "queued",
            }.get(action)
            if status is None:
                return {"error": f"Unsupported feedback action: {action}"}
            updated = await repo.async_update_user_signal_status(
                user_id=user_id,
                signal_id=signal_id,
                status=status,
            )
        return {"updated": bool(updated)}

    async def set_source_active(self, source_id: int, is_active: bool) -> dict[str, Any]:
        from app.infrastructure.persistence.repositories.signal_source_repository import (
            SqliteSignalSourceRepositoryAdapter,
        )

        runtime = await self.context.ensure_api_runtime()
        repo = SqliteSignalSourceRepositoryAdapter(runtime.db)
        user_id = self.context.user_id
        if user_id is None:
            return {"error": "Source updates require a scoped MCP user"}
        updated = await repo.async_set_user_source_active(
            user_id=user_id,
            source_id=source_id,
            is_active=is_active,
        )
        return {"updated": bool(updated), "is_active": bool(is_active)}

    @staticmethod
    def _source(row: Any) -> dict[str, Any]:
        return {
            "id": row.id,
            "kind": row.kind,
            "external_id": row.external_id,
            "url": row.url,
            "title": row.title,
            "is_active": row.is_active,
            "fetch_error_count": row.fetch_error_count,
            "last_error": row.last_error,
        }

    @staticmethod
    def _signal(row: Any) -> dict[str, Any]:
        return {
            "id": row.id,
            "status": row.status,
            "final_score": row.final_score,
            "filter_stage": row.filter_stage,
            "title": row.feed_item.title,
            "url": row.feed_item.canonical_url,
            "source_kind": row.feed_item.source.kind,
            "source_title": row.feed_item.source.title,
            "topic_name": row.topic.name if row.topic_id else None,
        }
