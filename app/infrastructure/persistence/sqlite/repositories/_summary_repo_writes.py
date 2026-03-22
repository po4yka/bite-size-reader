"""Write operations for the SQLite summary repository."""

from __future__ import annotations

from typing import Any

from app.db.json_utils import prepare_json_payload
from app.db.models import Request, Summary
from app.domain.models.request import RequestStatus

from ._repository_mixin_base import SqliteRepositoryMixinBase
from ._summary_repo_shared import _upsert_summary_record


class SummaryRepositoryWriteMixin(SqliteRepositoryMixinBase):
    """Mutating summary persistence operations."""

    async def async_upsert_summary(
        self,
        request_id: int,
        lang: str,
        json_payload: dict[str, Any],
        insights_json: dict[str, Any] | None = None,
        is_read: bool = False,
    ) -> int:
        """Create or update a summary."""

        def _upsert() -> int:
            return _upsert_summary_record(
                request_id=request_id,
                lang=lang,
                json_payload=json_payload,
                insights_json=insights_json,
                is_read=is_read,
            )

        return await self._execute(_upsert, operation_name="upsert_summary")

    async def async_finalize_request_summary(
        self,
        request_id: int,
        lang: str,
        json_payload: dict[str, Any],
        insights_json: dict[str, Any] | None = None,
        is_read: bool = False,
        request_status: RequestStatus = RequestStatus.COMPLETED,
    ) -> int:
        """Persist a summary and update request status in one transaction."""

        def _finalize() -> int:
            version = _upsert_summary_record(
                request_id=request_id,
                lang=lang,
                json_payload=json_payload,
                insights_json=insights_json,
                is_read=is_read,
            )
            Request.update({Request.status: request_status}).where(
                Request.id == request_id
            ).execute()
            return version

        return await self._execute_transaction(
            _finalize,
            operation_name="finalize_request_summary",
        )

    async def async_update_summary_insights(
        self, request_id: int, insights_json: dict[str, Any]
    ) -> None:
        """Update the insights field of a summary."""

        def _update() -> None:
            insights = prepare_json_payload(insights_json)
            Summary.update({Summary.insights_json: insights}).where(
                Summary.request == request_id
            ).execute()

        await self._execute(_update, operation_name="update_summary_insights")
