"""Service logic for custom digest endpoints."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

from app.api.dependencies.database import get_session_manager
from app.api.exceptions import ResourceNotFoundError, ValidationError
from app.api.models.responses import CustomDigestResponse
from app.api.search_helpers import isotime

if TYPE_CHECKING:
    from app.api.models.requests import CreateCustomDigestRequest
    from app.db.session import DatabaseSessionManager


class CustomDigestService:
    """Owns custom digest creation and retrieval."""

    def __init__(self, session_manager: DatabaseSessionManager | None = None) -> None:
        self._db = session_manager or get_session_manager()

    async def create_digest(
        self,
        *,
        user_id: int,
        body: CreateCustomDigestRequest,
    ) -> dict[str, Any]:
        """Create a digest from owned summary IDs."""

        def _create() -> dict[str, Any]:
            from app.application.services.topic_search_utils import ensure_mapping
            from app.db.models import CustomDigest, Request, Summary

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
            found_ids = {summary.id for summary in summaries}
            missing = [sid for sid in summary_id_ints if sid not in found_ids]
            if missing:
                raise ValidationError(
                    "Some summary IDs not found or not owned by user",
                    details={"missing_ids": [str(item) for item in missing]},
                )

            content_parts: list[str] = []
            for summary in summaries:
                json_payload = ensure_mapping(summary.json_payload)
                metadata = ensure_mapping(json_payload.get("metadata"))
                heading = (
                    metadata.get("title") or summary.request.input_url or f"Summary {summary.id}"
                )
                summary_text = json_payload.get("summary_250", "")
                content_parts.append(f"## {heading}\n\n{summary_text}")

            digest = CustomDigest.create(
                id=uuid.uuid4(),
                user=user_id,
                title=body.title,
                summary_ids=json.dumps([str(item) for item in summary_id_ints]),
                format=body.format,
                content="\n\n---\n\n".join(content_parts),
                status="ready",
            )
            return self._digest_to_response(digest).model_dump(by_alias=True)

        return await self._db.async_execute(_create, operation_name="create_custom_digest")

    async def list_digests(self, *, user_id: int) -> list[dict[str, Any]]:
        """List digests owned by the user."""

        def _query() -> list[dict[str, Any]]:
            from app.db.models import CustomDigest

            digests = (
                CustomDigest.select()
                .where(CustomDigest.user == user_id)
                .order_by(CustomDigest.created_at.desc())
            )
            return [
                self._digest_to_response(digest).model_dump(by_alias=True) for digest in digests
            ]

        return await self._db.async_execute(
            _query,
            operation_name="list_custom_digests",
            read_only=True,
        )

    async def get_digest(self, *, user_id: int, digest_id: str) -> dict[str, Any]:
        """Get a single digest if owned by the user."""

        def _query() -> dict[str, Any]:
            from app.db.models import CustomDigest

            try:
                digest = CustomDigest.get_by_id(digest_id)
            except CustomDigest.DoesNotExist as exc:
                raise ResourceNotFoundError("CustomDigest", digest_id) from exc

            if str(digest.user_id) != str(user_id):
                raise ResourceNotFoundError("CustomDigest", digest_id)
            return self._digest_to_response(digest).model_dump(by_alias=True)

        return await self._db.async_execute(
            _query,
            operation_name="get_custom_digest",
            read_only=True,
        )

    @staticmethod
    def _digest_to_response(digest: Any) -> CustomDigestResponse:
        return CustomDigestResponse(
            id=str(digest.id),
            title=digest.title,
            content=digest.content,
            status=digest.status,
            created_at=isotime(digest.created_at),
        )
