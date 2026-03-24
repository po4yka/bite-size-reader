"""Service logic for summary highlight endpoints."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.api.dependencies.database import get_session_manager
from app.api.exceptions import ResourceNotFoundError
from app.api.models.responses import HighlightResponse
from app.api.search_helpers import isotime

if TYPE_CHECKING:
    from app.api.models.requests import CreateHighlightRequest, UpdateHighlightRequest
    from app.db.session import DatabaseSessionManager


class SummaryHighlightService:
    """Owns highlight persistence and summary ownership checks."""

    def __init__(self, session_manager: DatabaseSessionManager | None = None) -> None:
        self._db = session_manager or get_session_manager()

    async def list_highlights(self, *, user_id: int, summary_id: int) -> list[dict[str, Any]]:
        """List highlights for an owned summary."""

        def _query() -> list[dict[str, Any]]:
            from app.db.models import SummaryHighlight

            self._verify_summary_ownership(summary_id=summary_id, user_id=user_id)
            highlights = (
                SummaryHighlight.select()
                .where(
                    (SummaryHighlight.user == user_id) & (SummaryHighlight.summary == summary_id)
                )
                .order_by(SummaryHighlight.created_at.asc())
            )
            return [self._highlight_to_payload(highlight) for highlight in highlights]

        return await self._db.async_execute(
            _query,
            operation_name="list_summary_highlights",
            read_only=True,
        )

    async def create_highlight(
        self,
        *,
        user_id: int,
        summary_id: int,
        body: CreateHighlightRequest,
    ) -> dict[str, Any]:
        """Create a highlight for an owned summary."""

        def _create() -> dict[str, Any]:
            from app.db.models import SummaryHighlight

            self._verify_summary_ownership(summary_id=summary_id, user_id=user_id)
            highlight = SummaryHighlight.create(
                id=uuid.uuid4(),
                user=user_id,
                summary=summary_id,
                text=body.text,
                start_offset=body.start_offset,
                end_offset=body.end_offset,
                color=body.color,
                note=body.note,
            )
            return self._highlight_to_payload(highlight)

        return await self._db.async_execute(_create, operation_name="create_summary_highlight")

    async def update_highlight(
        self,
        *,
        user_id: int,
        summary_id: int,
        highlight_id: str,
        body: UpdateHighlightRequest,
    ) -> dict[str, Any]:
        """Update a highlight owned by the user."""

        def _update() -> dict[str, Any]:
            highlight = self._get_owned_highlight(
                user_id=user_id,
                summary_id=summary_id,
                highlight_id=highlight_id,
            )
            if body.color is not None:
                highlight.color = body.color
            if body.note is not None:
                highlight.note = body.note
            highlight.save()
            return self._highlight_to_payload(highlight)

        return await self._db.async_execute(_update, operation_name="update_summary_highlight")

    async def delete_highlight(
        self,
        *,
        user_id: int,
        summary_id: int,
        highlight_id: str,
    ) -> None:
        """Delete a highlight owned by the user."""

        def _delete() -> None:
            highlight = self._get_owned_highlight(
                user_id=user_id,
                summary_id=summary_id,
                highlight_id=highlight_id,
            )
            highlight.delete_instance()

        await self._db.async_execute(_delete, operation_name="delete_summary_highlight")

    @staticmethod
    def _verify_summary_ownership(*, summary_id: int, user_id: int) -> None:
        from app.db.models import Request, Summary

        try:
            summary = Summary.get_by_id(summary_id)
        except Summary.DoesNotExist:
            raise ResourceNotFoundError("Summary", summary_id) from None

        request = Request.get_by_id(summary.request_id)
        if request.user_id != user_id:
            raise ResourceNotFoundError("Summary", summary_id)

    def _get_owned_highlight(
        self,
        *,
        user_id: int,
        summary_id: int,
        highlight_id: str,
    ) -> Any:
        from app.db.models import SummaryHighlight

        self._verify_summary_ownership(summary_id=summary_id, user_id=user_id)
        try:
            return SummaryHighlight.get(
                (SummaryHighlight.id == highlight_id)
                & (SummaryHighlight.user == user_id)
                & (SummaryHighlight.summary == summary_id)
            )
        except SummaryHighlight.DoesNotExist:
            raise ResourceNotFoundError("Highlight", highlight_id) from None

    @staticmethod
    def _highlight_to_payload(highlight: Any) -> dict[str, Any]:
        return HighlightResponse(
            id=str(highlight.id),
            summary_id=str(highlight.summary_id),
            text=highlight.text,
            start_offset=highlight.start_offset,
            end_offset=highlight.end_offset,
            color=highlight.color,
            note=highlight.note,
            created_at=isotime(highlight.created_at),
            updated_at=isotime(highlight.updated_at),
        ).model_dump(by_alias=True)
