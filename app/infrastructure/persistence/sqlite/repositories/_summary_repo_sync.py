"""Sync, analytics, and server-version operations for the SQLite summary repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import peewee

from app.db.models import Request, Summary, model_to_dict

from ._repository_mixin_base import SqliteRepositoryMixinBase

if TYPE_CHECKING:
    from datetime import datetime


class SummaryRepositorySyncMixin(SqliteRepositoryMixinBase):
    """Analytics and sync-oriented summary operations."""

    async def async_get_user_summaries_for_insights(
        self,
        user_id: int,
        request_created_after: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Get summary+request rows for analytics and insight computations."""

        def _query() -> list[dict[str, Any]]:
            if limit <= 0:
                return []

            rows = (
                Summary.select(Summary, Request)
                .join(Request)
                .where(
                    (Request.user_id == user_id)
                    & (Request.created_at >= request_created_after)
                    & (~Summary.is_deleted)
                )
                .order_by(Request.created_at.desc())
                .limit(limit)
            )
            return [model_to_dict(row) or {} for row in rows]

        return await self._execute(
            _query,
            operation_name="get_user_summaries_for_insights",
            read_only=True,
        )

    async def async_get_user_summary_activity_dates(
        self,
        user_id: int,
        created_after: datetime,
    ) -> list[Any]:
        """Return summary timestamps used for user streak calculations."""

        def _query() -> list[Any]:
            rows = (
                Summary.select(Summary.created_at)
                .join(Request)
                .where(
                    (Request.user_id == user_id)
                    & (Summary.created_at >= created_after)
                    & (~Summary.is_deleted)
                )
                .order_by(Summary.created_at.desc())
            )
            return [row.created_at for row in rows]

        return await self._execute(
            _query,
            operation_name="get_user_summary_activity_dates",
            read_only=True,
        )

    async def async_get_max_server_version(self, user_id: int) -> int | None:
        """Return the maximum server_version across summaries owned by *user_id*."""

        def _query() -> int | None:
            return (
                Summary.select(peewee.fn.MAX(Summary.server_version))
                .join(Request)
                .where(Request.user_id == user_id)
                .scalar()
            )

        return await self._execute(
            _query, operation_name="get_max_server_version_summary", read_only=True
        )

    async def async_get_all_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Get all summaries for a user for sync operations."""

        def _get() -> list[dict[str, Any]]:
            summaries = (
                Summary.select(Summary, Request).join(Request).where(Request.user_id == user_id)
            )
            result = []
            for summary in summaries:
                summary_dict = model_to_dict(summary) or {}
                if "request" in summary_dict and isinstance(summary_dict["request"], dict):
                    summary_dict["request"] = summary_dict["request"]["id"]
                result.append(summary_dict)
            return result

        return await self._execute(
            _get, operation_name="get_all_summaries_for_user", read_only=True
        )

    async def async_get_summary_for_sync_apply(
        self, summary_id: int, user_id: int
    ) -> dict[str, Any] | None:
        """Get a summary by ID for sync apply, validating user ownership."""

        def _get() -> dict[str, Any] | None:
            summary = (
                Summary.select(Summary, Request)
                .join(Request)
                .where((Summary.id == summary_id) & (Request.user_id == user_id))
                .first()
            )
            if not summary:
                return None
            return model_to_dict(summary) or {}

        return await self._execute(
            _get, operation_name="get_summary_for_sync_apply", read_only=True
        )

    async def async_apply_sync_change(
        self,
        summary_id: int,
        *,
        is_deleted: bool | None = None,
        deleted_at: datetime | None = None,
        is_read: bool | None = None,
    ) -> int:
        """Apply a sync change to a summary."""

        def _apply() -> int:
            update_fields: dict[Any, Any] = {}
            if is_deleted is not None:
                update_fields[Summary.is_deleted] = is_deleted
            if deleted_at is not None:
                update_fields[Summary.deleted_at] = deleted_at
            if is_read is not None:
                update_fields[Summary.is_read] = is_read

            if update_fields:
                Summary.update(update_fields).where(Summary.id == summary_id).execute()

            summary = Summary.get_or_none(Summary.id == summary_id)
            return int(summary.server_version or 0) if summary else 0

        return await self._execute(_apply, operation_name="apply_sync_change")
