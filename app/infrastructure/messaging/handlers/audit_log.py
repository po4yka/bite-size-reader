"""Audit log event handler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domain.events.request_events import RequestCompleted, RequestFailed
    from app.domain.events.summary_events import SummaryCreated
from app.infrastructure.persistence.sqlite.repositories.audit_log_repository import (
    SqliteAuditLogRepositoryAdapter,
)

logger = logging.getLogger(__name__)


class AuditLogEventHandler:
    """Persist audit logs for important domain events."""

    def __init__(self, database: Any) -> None:
        if isinstance(database, SqliteAuditLogRepositoryAdapter):
            self._repo = database
        else:
            self._repo = SqliteAuditLogRepositoryAdapter(database)

    async def on_summary_created(self, event: SummaryCreated) -> None:
        try:
            await self._repo.async_insert_audit_log(
                log_level="INFO",
                event_type="summary_created",
                details={
                    "summary_id": event.summary_id,
                    "request_id": event.request_id,
                    "language": event.language,
                    "has_insights": event.has_insights,
                    "timestamp": event.occurred_at.isoformat(),
                },
            )
        except Exception as exc:
            logger.warning(
                "audit_log_failed", extra={"event_type": "summary_created", "error": str(exc)}
            )

    async def on_request_completed(self, event: RequestCompleted) -> None:
        try:
            await self._repo.async_insert_audit_log(
                log_level="INFO",
                event_type="request_completed",
                details={
                    "request_id": event.request_id,
                    "summary_id": event.summary_id,
                    "timestamp": event.occurred_at.isoformat(),
                },
            )
        except Exception as exc:
            logger.warning(
                "audit_log_failed", extra={"event_type": "request_completed", "error": str(exc)}
            )

    async def on_request_failed(self, event: RequestFailed) -> None:
        try:
            await self._repo.async_insert_audit_log(
                log_level="ERROR",
                event_type="request_failed",
                details={
                    "request_id": event.request_id,
                    "error_message": event.error_message,
                    "error_details": event.error_details,
                    "timestamp": event.occurred_at.isoformat(),
                },
            )
        except Exception as exc:
            logger.warning(
                "audit_log_failed", extra={"event_type": "request_failed", "error": str(exc)}
            )
