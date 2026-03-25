"""Rule engine EventBus handler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from app.application.ports.requests import RequestRepositoryPort
    from app.application.use_cases.rule_execution import RuleExecutionUseCase
    from app.domain.events.request_events import RequestCompleted, RequestFailed
    from app.domain.events.summary_events import SummaryCreated
    from app.domain.events.tag_events import TagAttached, TagDetached

logger = get_logger(__name__)


class RuleEngineHandler:
    """EventBus subscriber that triggers rule evaluation on domain events."""

    def __init__(
        self,
        rule_execution_use_case: RuleExecutionUseCase,
        request_repository: RequestRepositoryPort,
    ) -> None:
        self._rule_execution = rule_execution_use_case
        self._request_repository = request_repository

    async def _user_id_from_request(self, request_id: int) -> int | None:
        request = await self._request_repository.async_get_request_by_id(request_id)
        if request is None:
            logger.warning("rule_engine_request_not_found", extra={"request_id": request_id})
            return None
        user_id = request.get("user_id")
        return int(user_id) if user_id is not None else None

    async def on_summary_created(self, event: SummaryCreated) -> None:
        user_id = await self._user_id_from_request(event.request_id)
        if user_id is None:
            return
        await self._safe_execute(
            user_id=user_id,
            event_type="summary.created",
            event_data={
                "summary_id": event.summary_id,
                "request_id": event.request_id,
                "language": event.language,
                "has_insights": event.has_insights,
            },
        )

    async def on_request_completed(self, event: RequestCompleted) -> None:
        user_id = await self._user_id_from_request(event.request_id)
        if user_id is None:
            return
        await self._safe_execute(
            user_id=user_id,
            event_type="request.completed",
            event_data={"request_id": event.request_id, "summary_id": event.summary_id},
        )

    async def on_request_failed(self, event: RequestFailed) -> None:
        user_id = await self._user_id_from_request(event.request_id)
        if user_id is None:
            return
        await self._safe_execute(
            user_id=user_id,
            event_type="request.failed",
            event_data={
                "request_id": event.request_id,
                "error_message": event.error_message,
                "error_details": event.error_details,
            },
        )

    async def on_tag_attached(self, event: TagAttached) -> None:
        await self._safe_execute(
            user_id=event.user_id,
            event_type="tag.attached",
            event_data={
                "summary_id": event.summary_id,
                "tag_id": event.tag_id,
                "source": event.source,
            },
        )

    async def on_tag_detached(self, event: TagDetached) -> None:
        await self._safe_execute(
            user_id=event.user_id,
            event_type="tag.detached",
            event_data={"summary_id": event.summary_id, "tag_id": event.tag_id},
        )

    async def _safe_execute(self, *, user_id: int, event_type: str, event_data: dict) -> None:
        try:
            results = await self._rule_execution.evaluate_and_execute(
                user_id, event_type, event_data
            )
            logger.info(
                "rule_engine_evaluated",
                extra={
                    "event_type": event_type,
                    "user_id": user_id,
                    "rules_evaluated": len(results),
                },
            )
        except Exception:
            logger.exception(
                "rule_engine_handler_error",
                extra={"event_type": event_type, "user_id": user_id},
            )
