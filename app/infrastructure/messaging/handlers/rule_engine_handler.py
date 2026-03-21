"""Rule engine EventBus handler.

Subscribes to domain events and triggers rule evaluation via the
rule execution use case. Stateless -- resolves user_id from the
Request table when not available directly on the event.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.use_cases.rule_execution import evaluate_and_execute
from app.core.logging_utils import get_logger
from app.db.models import Request

if TYPE_CHECKING:
    from app.domain.events.request_events import RequestCompleted, RequestFailed
    from app.domain.events.summary_events import SummaryCreated
    from app.domain.events.tag_events import TagAttached, TagDetached

logger = get_logger(__name__)


class RuleEngineHandler:
    """EventBus subscriber that triggers rule evaluation on domain events."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _user_id_from_request(self, request_id: int) -> int | None:
        """Look up user_id from the Request table (sync)."""
        try:
            req = Request.get_by_id(request_id)
            return req.user_id
        except Request.DoesNotExist:
            logger.warning(
                "rule_engine_request_not_found",
                extra={"request_id": request_id},
            )
            return None

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def on_summary_created(self, event: SummaryCreated) -> None:
        user_id = self._user_id_from_request(event.request_id)
        if user_id is None:
            return
        try:
            results = await evaluate_and_execute(
                user_id,
                "summary.created",
                {
                    "summary_id": event.summary_id,
                    "request_id": event.request_id,
                    "language": event.language,
                    "has_insights": event.has_insights,
                },
            )
            logger.info(
                "rule_engine_evaluated",
                extra={
                    "event_type": "summary.created",
                    "user_id": user_id,
                    "rules_evaluated": len(results),
                },
            )
        except Exception:
            logger.exception(
                "rule_engine_handler_error",
                extra={"event_type": "summary.created", "user_id": user_id},
            )

    async def on_request_completed(self, event: RequestCompleted) -> None:
        user_id = self._user_id_from_request(event.request_id)
        if user_id is None:
            return
        try:
            results = await evaluate_and_execute(
                user_id,
                "request.completed",
                {
                    "request_id": event.request_id,
                    "summary_id": event.summary_id,
                },
            )
            logger.info(
                "rule_engine_evaluated",
                extra={
                    "event_type": "request.completed",
                    "user_id": user_id,
                    "rules_evaluated": len(results),
                },
            )
        except Exception:
            logger.exception(
                "rule_engine_handler_error",
                extra={"event_type": "request.completed", "user_id": user_id},
            )

    async def on_request_failed(self, event: RequestFailed) -> None:
        user_id = self._user_id_from_request(event.request_id)
        if user_id is None:
            return
        try:
            results = await evaluate_and_execute(
                user_id,
                "request.failed",
                {
                    "request_id": event.request_id,
                    "error_message": event.error_message,
                    "error_details": event.error_details,
                },
            )
            logger.info(
                "rule_engine_evaluated",
                extra={
                    "event_type": "request.failed",
                    "user_id": user_id,
                    "rules_evaluated": len(results),
                },
            )
        except Exception:
            logger.exception(
                "rule_engine_handler_error",
                extra={"event_type": "request.failed", "user_id": user_id},
            )

    async def on_tag_attached(self, event: TagAttached) -> None:
        try:
            results = await evaluate_and_execute(
                event.user_id,
                "tag.attached",
                {
                    "summary_id": event.summary_id,
                    "tag_id": event.tag_id,
                    "source": event.source,
                },
            )
            logger.info(
                "rule_engine_evaluated",
                extra={
                    "event_type": "tag.attached",
                    "user_id": event.user_id,
                    "rules_evaluated": len(results),
                },
            )
        except Exception:
            logger.exception(
                "rule_engine_handler_error",
                extra={"event_type": "tag.attached", "user_id": event.user_id},
            )

    async def on_tag_detached(self, event: TagDetached) -> None:
        try:
            results = await evaluate_and_execute(
                event.user_id,
                "tag.detached",
                {
                    "summary_id": event.summary_id,
                    "tag_id": event.tag_id,
                },
            )
            logger.info(
                "rule_engine_evaluated",
                extra={
                    "event_type": "tag.detached",
                    "user_id": event.user_id,
                    "rules_evaluated": len(results),
                },
            )
        except Exception:
            logger.exception(
                "rule_engine_handler_error",
                extra={"event_type": "tag.detached", "user_id": event.user_id},
            )
