"""Apply-side helpers for sync flows."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.api.models.responses import SyncApplyItemResult
from app.core.time_utils import UTC

if TYPE_CHECKING:
    from .serializer import SyncEnvelopeSerializer


class SyncApplyService:
    def __init__(self, *, summary_repository: Any, serializer: SyncEnvelopeSerializer) -> None:
        self._summary_repo = summary_repository
        self._serializer = serializer

    async def apply_summary_change(self, change: Any, user_id: int) -> SyncApplyItemResult:
        try:
            summary_id = int(change.id)
        except (ValueError, TypeError):
            return SyncApplyItemResult(
                entity_type=change.entity_type,
                id=change.id,
                status="invalid",
                error_code="INVALID_ID",
            )

        summary = await self._summary_repo.async_get_summary_for_sync_apply(summary_id, user_id)
        if not summary:
            return SyncApplyItemResult(
                entity_type=change.entity_type,
                id=change.id,
                status="invalid",
                error_code="NOT_FOUND",
            )

        current_version = int(summary.get("server_version") or 0)
        if change.last_seen_version < current_version:
            snapshot = self._serializer.serialize_summary(summary).model_dump()
            return SyncApplyItemResult(
                entity_type=change.entity_type,
                id=change.id,
                status="conflict",
                server_version=current_version,
                server_snapshot=snapshot,
                error_code="CONFLICT_VERSION",
            )

        payload = change.payload or {}
        allowed_fields = {"is_read"}
        invalid_fields = [field for field in payload if field not in allowed_fields]
        if invalid_fields:
            return SyncApplyItemResult(
                entity_type=change.entity_type,
                id=change.id,
                status="invalid",
                error_code="INVALID_FIELDS",
                server_version=current_version,
            )

        is_deleted = None
        deleted_at = None
        is_read = None
        if change.action == "delete":
            is_deleted = True
            deleted_at = datetime.now(UTC)
        elif "is_read" in payload:
            is_read = bool(payload["is_read"])

        new_version = await self._summary_repo.async_apply_sync_change(
            summary_id,
            is_deleted=is_deleted,
            deleted_at=deleted_at,
            is_read=is_read,
        )

        return SyncApplyItemResult(
            entity_type=change.entity_type,
            id=change.id,
            status="applied",
            server_version=new_version,
        )
