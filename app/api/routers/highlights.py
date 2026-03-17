"""Highlight management endpoints for summaries."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends

from app.api.exceptions import ResourceNotFoundError
from app.api.models.requests import CreateHighlightRequest, UpdateHighlightRequest
from app.api.models.responses import HighlightListResponse, HighlightResponse, success_response
from app.api.routers.auth import get_current_user
from app.api.search_helpers import isotime
from app.core.logging_utils import get_logger
from app.db.models import SummaryHighlight

logger = get_logger(__name__)
router = APIRouter()


def _verify_summary_ownership(summary_id: int, user_id: int) -> None:
    """Verify that the summary belongs to the user via its request."""
    from app.db.models import Request, Summary

    try:
        summary = Summary.get_by_id(summary_id)
    except Summary.DoesNotExist:
        raise ResourceNotFoundError("Summary", summary_id) from None

    request = Request.get_by_id(summary.request_id)
    if request.user_id != user_id:
        raise ResourceNotFoundError("Summary", summary_id)


def _highlight_to_response(h: SummaryHighlight) -> HighlightResponse:
    """Convert a SummaryHighlight model instance to a response."""
    return HighlightResponse(
        id=str(h.id),
        summary_id=str(h.summary_id),
        text=h.text,
        start_offset=h.start_offset,
        end_offset=h.end_offset,
        color=h.color,
        note=h.note,
        created_at=isotime(h.created_at),
        updated_at=isotime(h.updated_at),
    )


@router.get("/{summary_id}/highlights")
def list_highlights(
    summary_id: int,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List all highlights for a summary."""
    _verify_summary_ownership(summary_id, user["user_id"])

    highlights = (
        SummaryHighlight.select()
        .where(
            (SummaryHighlight.user == user["user_id"]) & (SummaryHighlight.summary == summary_id)
        )
        .order_by(SummaryHighlight.created_at.asc())
    )

    items = [_highlight_to_response(h) for h in highlights]
    return success_response(HighlightListResponse(highlights=items))


@router.post("/{summary_id}/highlights", status_code=201)
def create_highlight(
    summary_id: int,
    body: CreateHighlightRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a highlight on a summary."""
    _verify_summary_ownership(summary_id, user["user_id"])

    highlight = SummaryHighlight.create(
        id=uuid.uuid4(),
        user=user["user_id"],
        summary=summary_id,
        text=body.text,
        start_offset=body.start_offset,
        end_offset=body.end_offset,
        color=body.color,
        note=body.note,
    )

    return success_response(_highlight_to_response(highlight))


@router.patch("/{summary_id}/highlights/{highlight_id}")
def update_highlight(
    summary_id: int,
    highlight_id: str,
    body: UpdateHighlightRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Update a highlight's color or note."""
    _verify_summary_ownership(summary_id, user["user_id"])

    try:
        highlight = SummaryHighlight.get(
            (SummaryHighlight.id == highlight_id)
            & (SummaryHighlight.user == user["user_id"])
            & (SummaryHighlight.summary == summary_id)
        )
    except SummaryHighlight.DoesNotExist:
        raise ResourceNotFoundError("Highlight", highlight_id) from None

    if body.color is not None:
        highlight.color = body.color
    if body.note is not None:
        highlight.note = body.note
    highlight.save()

    return success_response(_highlight_to_response(highlight))


@router.delete("/{summary_id}/highlights/{highlight_id}")
def delete_highlight(
    summary_id: int,
    highlight_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete a highlight."""
    _verify_summary_ownership(summary_id, user["user_id"])

    try:
        highlight = SummaryHighlight.get(
            (SummaryHighlight.id == highlight_id)
            & (SummaryHighlight.user == user["user_id"])
            & (SummaryHighlight.summary == summary_id)
        )
    except SummaryHighlight.DoesNotExist:
        raise ResourceNotFoundError("Highlight", highlight_id) from None

    highlight.delete_instance()
    return success_response({"deleted": True, "id": str(highlight_id)})
