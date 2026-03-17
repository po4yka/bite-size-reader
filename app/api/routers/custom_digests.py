"""Custom digest endpoints.

Allows users to create digests from selected summaries.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends

from app.api.exceptions import ResourceNotFoundError, ValidationError
from app.api.models.requests import CreateCustomDigestRequest  # noqa: TC001
from app.api.models.responses import CustomDigestResponse, success_response
from app.api.routers.auth import get_current_user
from app.api.search_helpers import isotime
from app.core.logging_utils import get_logger

logger = get_logger(__name__)
router = APIRouter()


def _digest_to_response(digest: Any) -> CustomDigestResponse:
    """Convert a CustomDigest model instance to a response."""
    return CustomDigestResponse(
        id=str(digest.id),
        title=digest.title,
        content=digest.content,
        status=digest.status,
        created_at=isotime(digest.created_at),
    )


@router.post("")
async def create_custom_digest(
    body: CreateCustomDigestRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a custom digest from a list of summary IDs."""
    from app.application.services.topic_search_utils import ensure_mapping
    from app.db.models import CustomDigest, Request, Summary

    user_id = user["user_id"]

    # Validate all summary IDs belong to the current user
    summary_id_ints: list[int] = []
    for sid in body.summary_ids:
        try:
            summary_id_ints.append(int(sid))
        except (ValueError, TypeError) as exc:
            raise ValidationError(
                f"Invalid summary ID: {sid}", details={"summary_id": sid}
            ) from exc

    summaries = list(
        Summary.select(Summary, Request)
        .join(Request)
        .where(
            Summary.id.in_(summary_id_ints),
            Request.user_id == user_id,
            Summary.is_deleted == False,  # noqa: E712
        )
    )

    found_ids = {s.id for s in summaries}
    missing = [sid for sid in summary_id_ints if sid not in found_ids]
    if missing:
        raise ValidationError(
            "Some summary IDs not found or not owned by user",
            details={"missing_ids": [str(m) for m in missing]},
        )

    # Generate content by concatenating summaries
    content_parts: list[str] = []
    for s in summaries:
        json_payload = ensure_mapping(s.json_payload)
        metadata = ensure_mapping(json_payload.get("metadata"))
        heading = metadata.get("title") or s.request.input_url or f"Summary {s.id}"
        summary_text = json_payload.get("summary_250", "")
        content_parts.append(f"## {heading}\n\n{summary_text}")

    content = "\n\n---\n\n".join(content_parts)

    digest = CustomDigest.create(
        id=uuid.uuid4(),
        user=user_id,
        title=body.title,
        summary_ids=json.dumps([str(sid) for sid in summary_id_ints]),
        format=body.format,
        content=content,
        status="ready",
    )

    return success_response(_digest_to_response(digest))


@router.get("")
async def list_custom_digests(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List all custom digests for the current user, newest first."""
    from app.db.models import CustomDigest

    digests = list(
        CustomDigest.select()
        .where(CustomDigest.user == user["user_id"])
        .order_by(CustomDigest.created_at.desc())
    )

    return success_response(
        {"digests": [_digest_to_response(d).model_dump(by_alias=True) for d in digests]}
    )


@router.get("/{digest_id}")
async def get_custom_digest(
    digest_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a specific custom digest by ID."""
    from app.db.models import CustomDigest

    try:
        digest = CustomDigest.get_by_id(digest_id)
    except CustomDigest.DoesNotExist as exc:
        raise ResourceNotFoundError("CustomDigest", digest_id) from exc

    if str(digest.user_id) != str(user["user_id"]):
        raise ResourceNotFoundError("CustomDigest", digest_id)

    return success_response(_digest_to_response(digest))
