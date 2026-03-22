"""State mutation and feedback operations for the SQLite summary repository."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from app.core.time_utils import UTC
from app.db.models import Summary, SummaryFeedback

from ._repository_mixin_base import SqliteRepositoryMixinBase


class SummaryRepositoryStateMixin(SqliteRepositoryMixinBase):
    """Summary state transition and feedback operations."""

    async def async_mark_summary_as_read(self, summary_id: int) -> None:
        """Mark a summary as read."""

        def _update() -> None:
            Summary.update({Summary.is_read: True}).where(Summary.id == summary_id).execute()

        await self._execute(_update, operation_name="mark_summary_as_read")

    async def async_mark_summary_as_unread(self, summary_id: int) -> None:
        """Mark a summary as unread."""

        def _update() -> None:
            Summary.update({Summary.is_read: False}).where(Summary.id == summary_id).execute()

        await self._execute(_update, operation_name="mark_summary_as_unread")

    async def async_mark_summary_as_read_by_request(self, request_id: int) -> None:
        """Mark a summary as read by its request ID."""

        def _update() -> None:
            Summary.update({Summary.is_read: True}).where(Summary.request == request_id).execute()

        await self._execute(_update, operation_name="mark_summary_as_read_by_request")

    async def async_get_read_status(self, request_id: int) -> bool:
        """Return whether the summary for a given request is marked as read."""

        def _get() -> bool:
            summary = Summary.get_or_none(Summary.request == request_id)
            return bool(summary.is_read) if summary else False

        result = await self._execute(_get, operation_name="get_read_status", read_only=True)
        return bool(result)

    async def async_update_reading_progress(
        self,
        summary_id: int,
        progress: float,
        last_read_offset: int,
    ) -> None:
        """Update reading progress and offset for a summary."""

        def _update() -> None:
            Summary.update(
                {
                    Summary.reading_progress: progress,
                    Summary.last_read_offset: last_read_offset,
                    Summary.updated_at: datetime.now(UTC),
                }
            ).where(Summary.id == summary_id).execute()

        await self._execute(_update, operation_name="update_reading_progress")

    async def async_soft_delete_summary(self, summary_id: int) -> None:
        """Soft delete a summary."""

        def _update() -> None:
            Summary.update({Summary.is_deleted: True, Summary.deleted_at: datetime.now(UTC)}).where(
                Summary.id == summary_id
            ).execute()

        await self._execute(_update, operation_name="soft_delete_summary")

    async def async_toggle_favorite(self, summary_id: int) -> bool:
        """Toggle favorite status of a summary."""

        def _toggle() -> bool:
            summary = Summary.get_by_id(summary_id)
            new_value = not summary.is_favorited
            summary.is_favorited = new_value
            summary.save()
            return new_value

        return await self._execute(_toggle, operation_name="toggle_favorite")

    async def async_set_favorite(self, summary_id: int, value: bool) -> None:
        """Persist an explicit favorite status for a summary."""

        def _set() -> None:
            Summary.update({Summary.is_favorited: value}).where(Summary.id == summary_id).execute()

        await self._execute(_set, operation_name="set_favorite")

    async def async_upsert_feedback(
        self,
        user_id: int,
        summary_id: int,
        rating: int | None,
        issues: list[str] | None,
        comment: str | None,
    ) -> dict[str, Any]:
        """Create or update feedback for a summary."""

        def _upsert() -> dict[str, Any]:
            feedback, created = SummaryFeedback.get_or_create(
                user=user_id,
                summary=summary_id,
                defaults={
                    "id": uuid.uuid4(),
                    "rating": rating,
                    "issues": json.dumps(issues) if issues is not None else None,
                    "comment": comment,
                },
            )
            if not created:
                if rating is not None:
                    feedback.rating = rating
                if issues is not None:
                    feedback.issues = json.dumps(issues)
                if comment is not None:
                    feedback.comment = comment
                feedback.save()

            issues_value: list[str] | None = None
            if feedback.issues:
                issues_value = json.loads(feedback.issues)
            return {
                "id": str(feedback.id),
                "rating": feedback.rating,
                "issues": issues_value,
                "comment": feedback.comment,
                "created_at": feedback.created_at,
            }

        return await self._execute(_upsert, operation_name="upsert_feedback")
