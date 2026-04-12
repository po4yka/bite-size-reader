"""SQLite implementation of aggregation session repository."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.core.time_utils import UTC
from app.db.json_utils import prepare_json_payload
from app.db.models import AggregationSession, AggregationSessionItem, model_to_dict
from app.domain.models.source import AggregationItemStatus, AggregationSessionStatus, SourceItem
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository

if TYPE_CHECKING:
    from app.application.dto.aggregation import AggregationFailure, NormalizedSourceDocument


def _status_value(status: AggregationItemStatus | AggregationSessionStatus | str) -> str:
    return status.value if hasattr(status, "value") else str(status)


class SqliteAggregationSessionRepositoryAdapter(SqliteBaseRepository):
    """Adapter for aggregation bundle persistence operations."""

    async def async_create_aggregation_session(
        self,
        user_id: int,
        correlation_id: str,
        total_items: int,
        *,
        allow_partial_success: bool = True,
        bundle_metadata: dict[str, Any] | None = None,
    ) -> int:
        def _create() -> int:
            session = AggregationSession.create(
                user=user_id,
                correlation_id=correlation_id,
                total_items=total_items,
                allow_partial_success=allow_partial_success,
                bundle_metadata_json=prepare_json_payload(bundle_metadata),
                status=AggregationSessionStatus.PENDING.value,
            )
            return session.id

        return await self._execute(_create, operation_name="create_aggregation_session")

    async def async_get_aggregation_session(self, session_id: int) -> dict[str, Any] | None:
        def _get() -> dict[str, Any] | None:
            session = AggregationSession.get_or_none(AggregationSession.id == session_id)
            return model_to_dict(session)

        return await self._execute(
            _get,
            operation_name="get_aggregation_session",
            read_only=True,
        )

    async def async_get_aggregation_session_by_correlation_id(
        self, correlation_id: str
    ) -> dict[str, Any] | None:
        def _get() -> dict[str, Any] | None:
            session = AggregationSession.get_or_none(
                AggregationSession.correlation_id == correlation_id
            )
            return model_to_dict(session)

        return await self._execute(
            _get,
            operation_name="get_aggregation_session_by_correlation_id",
            read_only=True,
        )

    async def async_add_aggregation_session_item(
        self,
        session_id: int,
        source_item: SourceItem,
        position: int,
        *,
        request_id: int | None = None,
    ) -> int:
        def _create() -> int:
            first_match = (
                AggregationSessionItem.select(AggregationSessionItem.id)
                .where(
                    (AggregationSessionItem.aggregation_session == session_id)
                    & (AggregationSessionItem.source_item_id == source_item.stable_id)
                    & AggregationSessionItem.duplicate_of_item_id.is_null(True)
                )
                .order_by(AggregationSessionItem.position)
                .first()
            )
            item = AggregationSessionItem.create(
                aggregation_session=session_id,
                request=request_id,
                position=position,
                source_kind=source_item.kind.value,
                source_item_id=source_item.stable_id,
                source_dedupe_key=source_item.dedupe_key,
                original_value=source_item.original_value,
                normalized_value=source_item.normalized_value,
                external_id=source_item.external_id,
                telegram_chat_id=source_item.telegram_chat_id,
                telegram_message_id=source_item.telegram_message_id,
                telegram_media_group_id=source_item.telegram_media_group_id,
                title_hint=source_item.title_hint,
                source_metadata_json=prepare_json_payload(source_item.metadata),
                status=(
                    AggregationItemStatus.DUPLICATE.value
                    if first_match is not None
                    else AggregationItemStatus.PENDING.value
                ),
                duplicate_of_item_id=first_match.id if first_match is not None else None,
            )
            return item.id

        return await self._execute(_create, operation_name="add_aggregation_session_item")

    async def async_get_aggregation_session_items(self, session_id: int) -> list[dict[str, Any]]:
        def _get() -> list[dict[str, Any]]:
            items = (
                AggregationSessionItem.select()
                .where(AggregationSessionItem.aggregation_session == session_id)
                .order_by(AggregationSessionItem.position)
            )
            return [model_to_dict(item) or {} for item in items]

        return await self._execute(
            _get,
            operation_name="get_aggregation_session_items",
            read_only=True,
        )

    async def async_update_aggregation_session_item_result(
        self,
        item_id: int,
        *,
        status: AggregationItemStatus | str,
        request_id: int | None = None,
        normalized_document: NormalizedSourceDocument | None = None,
        extraction_metadata: dict[str, Any] | None = None,
        failure: AggregationFailure | None = None,
    ) -> None:
        def _update() -> None:
            update_fields: dict[Any, Any] = {
                AggregationSessionItem.status: _status_value(status),
                AggregationSessionItem.updated_at: datetime.now(UTC),
            }
            if request_id is not None:
                update_fields[AggregationSessionItem.request] = request_id
            if normalized_document is not None:
                update_fields[AggregationSessionItem.normalized_document_json] = (
                    prepare_json_payload(normalized_document.model_dump(mode="json"))
                )
            if extraction_metadata is not None:
                update_fields[AggregationSessionItem.extraction_metadata_json] = (
                    prepare_json_payload(extraction_metadata)
                )
            if failure is not None:
                update_fields[AggregationSessionItem.failure_code] = failure.code
                update_fields[AggregationSessionItem.failure_message] = failure.message
                update_fields[AggregationSessionItem.failure_details_json] = prepare_json_payload(
                    failure.details
                )
            elif _status_value(status) != AggregationItemStatus.FAILED.value:
                update_fields[AggregationSessionItem.failure_code] = None
                update_fields[AggregationSessionItem.failure_message] = None
                update_fields[AggregationSessionItem.failure_details_json] = None

            AggregationSessionItem.update(update_fields).where(
                AggregationSessionItem.id == item_id
            ).execute()

        await self._execute(_update, operation_name="update_aggregation_session_item_result")

    async def async_update_aggregation_session_counts(
        self,
        session_id: int,
        *,
        successful_count: int,
        failed_count: int,
        duplicate_count: int,
    ) -> None:
        def _update() -> None:
            AggregationSession.update(
                {
                    AggregationSession.successful_count: successful_count,
                    AggregationSession.failed_count: failed_count,
                    AggregationSession.duplicate_count: duplicate_count,
                    AggregationSession.updated_at: datetime.now(UTC),
                }
            ).where(AggregationSession.id == session_id).execute()

        await self._execute(_update, operation_name="update_aggregation_session_counts")

    async def async_update_aggregation_session_status(
        self,
        session_id: int,
        *,
        status: AggregationSessionStatus | str,
        processing_time_ms: int | None = None,
        failure: AggregationFailure | None = None,
    ) -> None:
        def _update() -> None:
            update_fields: dict[Any, Any] = {
                AggregationSession.status: _status_value(status),
                AggregationSession.updated_at: datetime.now(UTC),
            }
            if processing_time_ms is not None:
                update_fields[AggregationSession.processing_time_ms] = processing_time_ms
            if failure is not None:
                update_fields[AggregationSession.failure_code] = failure.code
                update_fields[AggregationSession.failure_message] = failure.message
                update_fields[AggregationSession.failure_details_json] = prepare_json_payload(
                    failure.details
                )
            elif _status_value(status) != AggregationSessionStatus.FAILED.value:
                update_fields[AggregationSession.failure_code] = None
                update_fields[AggregationSession.failure_message] = None
                update_fields[AggregationSession.failure_details_json] = None

            AggregationSession.update(update_fields).where(
                AggregationSession.id == session_id
            ).execute()

        await self._execute(_update, operation_name="update_aggregation_session_status")
