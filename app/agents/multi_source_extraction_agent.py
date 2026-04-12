"""Mixed-source extraction orchestrator for aggregation bundles."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.content.multi_source_classification import build_source_item_from_submission
from app.agents.base_agent import AgentResult, BaseAgent
from app.application.dto.aggregation import (
    AggregationFailure,
    ExtractedTextKind,
    MultiSourceExtractionOutput,
    NormalizedSourceDocument,
    SourceExtractionItemResult,
    SourceMediaAsset,
    SourceMediaKind,
    SourceProvenance,
    SourceSubmission,
    SourceTextBlock,
)
from app.domain.models.source import (
    AggregationItemStatus,
    AggregationRequest,
    AggregationSessionStatus,
    SourceItem,
)

if TYPE_CHECKING:
    from app.adapters.content.content_extractor import ContentExtractor
    from app.application.ports.aggregation_sessions import AggregationSessionRepositoryPort


class MultiSourceExtractionInput(BaseModel):
    """Input bundle for the mixed-source extraction agent."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    correlation_id: str
    user_id: int
    items: list[SourceSubmission]
    allow_partial_success: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class MultiSourceExtractionAgent(
    BaseAgent[MultiSourceExtractionInput, MultiSourceExtractionOutput]
):
    """Orchestrate classification and extraction across heterogeneous source items."""

    def __init__(
        self,
        *,
        content_extractor: ContentExtractor,
        aggregation_session_repo: AggregationSessionRepositoryPort,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(name="MultiSourceExtractionAgent", correlation_id=correlation_id)
        self._content_extractor = content_extractor
        self._aggregation_session_repo = aggregation_session_repo

    async def execute(
        self, input_data: MultiSourceExtractionInput
    ) -> AgentResult[MultiSourceExtractionOutput]:
        """Classify and extract a mixed source bundle with partial-success semantics."""

        self.correlation_id = input_data.correlation_id
        self.log_info(
            "multi_source_extraction_started",
            total_items=len(input_data.items),
            allow_partial_success=input_data.allow_partial_success,
        )

        try:
            classified_items = [
                build_source_item_from_submission(item) for item in input_data.items
            ]
            aggregation_request = AggregationRequest.from_items(
                classified_items,
                correlation_id=input_data.correlation_id,
                user_id=input_data.user_id,
                allow_partial_success=input_data.allow_partial_success,
                metadata=input_data.metadata,
            )
        except Exception as exc:
            self.log_error("multi_source_input_invalid", error=str(exc))
            return AgentResult.error_result(
                f"Invalid aggregation input: {exc!s}",
                exception_type=type(exc).__name__,
            )

        session_id = await self._aggregation_session_repo.async_create_aggregation_session(
            user_id=input_data.user_id,
            correlation_id=input_data.correlation_id,
            total_items=aggregation_request.total_items,
            allow_partial_success=input_data.allow_partial_success,
            bundle_metadata=input_data.metadata,
        )
        await self._aggregation_session_repo.async_update_aggregation_session_status(
            session_id,
            status=AggregationSessionStatus.PROCESSING,
        )

        started = time.perf_counter()
        duplicate_positions = aggregation_request.bundle.duplicate_positions()
        item_results: list[SourceExtractionItemResult] = []
        successful_count = 0
        failed_count = 0
        duplicate_count = 0
        first_item_ids_by_source: dict[str, int] = {}

        for position, (submission, source_item) in enumerate(
            zip(input_data.items, aggregation_request.bundle.items, strict=True)
        ):
            item_id = await self._aggregation_session_repo.async_add_aggregation_session_item(
                session_id,
                source_item,
                position,
                request_id=source_item.request_id,
            )
            first_item_ids_by_source.setdefault(source_item.stable_id, item_id)

            duplicate_position = duplicate_positions.get(position)
            if duplicate_position is not None:
                duplicate_count += 1
                duplicate_of_item_id = first_item_ids_by_source[source_item.stable_id]
                item_results.append(
                    SourceExtractionItemResult(
                        position=position,
                        item_id=item_id,
                        source_item_id=source_item.stable_id,
                        source_kind=source_item.kind,
                        status=AggregationItemStatus.DUPLICATE.value,
                        request_id=source_item.request_id,
                        duplicate_of_item_id=duplicate_of_item_id,
                    )
                )
                continue

            await self._aggregation_session_repo.async_update_aggregation_session_item_result(
                item_id,
                status=AggregationItemStatus.PROCESSING,
                request_id=source_item.request_id,
            )
            try:
                (
                    request_id,
                    normalized_document,
                    extraction_metadata,
                ) = await self._extract_submission(
                    submission=submission,
                    source_item=source_item,
                    correlation_id=input_data.correlation_id,
                )
                await self._aggregation_session_repo.async_update_aggregation_session_item_result(
                    item_id,
                    status=AggregationItemStatus.EXTRACTED,
                    request_id=request_id,
                    normalized_document=normalized_document,
                    extraction_metadata=extraction_metadata,
                )
                successful_count += 1
                item_results.append(
                    SourceExtractionItemResult(
                        position=position,
                        item_id=item_id,
                        source_item_id=source_item.stable_id,
                        source_kind=source_item.kind,
                        status=AggregationItemStatus.EXTRACTED.value,
                        request_id=request_id,
                        normalized_document=normalized_document,
                        extraction_metadata=extraction_metadata,
                    )
                )
            except Exception as exc:
                failed_count += 1
                item_failure = AggregationFailure(
                    code="source_extraction_failed",
                    message=str(exc),
                    retryable=True,
                    details={
                        "source_kind": source_item.kind.value,
                        "exception_type": type(exc).__name__,
                    },
                )
                await self._aggregation_session_repo.async_update_aggregation_session_item_result(
                    item_id,
                    status=AggregationItemStatus.FAILED,
                    request_id=source_item.request_id,
                    failure=item_failure,
                )
                item_results.append(
                    SourceExtractionItemResult(
                        position=position,
                        item_id=item_id,
                        source_item_id=source_item.stable_id,
                        source_kind=source_item.kind,
                        status=AggregationItemStatus.FAILED.value,
                        request_id=source_item.request_id,
                        failure=item_failure,
                    )
                )
                self.log_warning(
                    "multi_source_item_failed",
                    position=position,
                    source_kind=source_item.kind.value,
                    error=str(exc),
                )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        await self._aggregation_session_repo.async_update_aggregation_session_counts(
            session_id,
            successful_count=successful_count,
            failed_count=failed_count,
            duplicate_count=duplicate_count,
        )
        session_status = self._resolve_session_status(
            successful_count=successful_count,
            failed_count=failed_count,
            duplicate_count=duplicate_count,
        )
        failure: AggregationFailure | None = None
        if successful_count == 0 and failed_count > 0:
            failure = AggregationFailure(
                code="all_sources_failed",
                message="All source extractions failed",
                retryable=True,
                details={"failed_count": failed_count},
            )
        await self._aggregation_session_repo.async_update_aggregation_session_status(
            session_id,
            status=session_status,
            processing_time_ms=elapsed_ms,
            failure=failure,
        )

        output = MultiSourceExtractionOutput(
            session_id=session_id,
            correlation_id=input_data.correlation_id,
            status=session_status.value,
            successful_count=successful_count,
            failed_count=failed_count,
            duplicate_count=duplicate_count,
            items=item_results,
        )
        if successful_count == 0 and duplicate_count == 0:
            return AgentResult.error_result(
                "All source extractions failed",
                session_id=session_id,
                status=session_status.value,
                failed_count=failed_count,
            )

        return AgentResult.success_result(
            output,
            session_id=session_id,
            status=session_status.value,
            successful_count=successful_count,
            failed_count=failed_count,
            duplicate_count=duplicate_count,
        )

    async def _extract_submission(
        self,
        *,
        submission: SourceSubmission,
        source_item: SourceItem,
        correlation_id: str,
    ) -> tuple[int | None, NormalizedSourceDocument, dict[str, Any]]:
        if submission.submission_kind.value == "url":
            return await self._extract_url_submission(
                url=submission.url or "",
                source_item=source_item,
                correlation_id=correlation_id,
            )

        return self._extract_telegram_submission(
            message=submission.telegram_message,
            source_item=source_item,
        )

    async def _extract_url_submission(
        self,
        *,
        url: str,
        source_item: SourceItem,
        correlation_id: str,
    ) -> tuple[int | None, NormalizedSourceDocument, dict[str, Any]]:
        content_text, content_source, metadata = await self._content_extractor.extract_content_pure(
            url=url,
            correlation_id=correlation_id,
            request_id=source_item.request_id,
        )
        request_id = _coerce_int(metadata.get("request_id"))
        title = _extract_title_from_metadata(metadata)
        normalized_document = NormalizedSourceDocument.from_extracted_content(
            source_item=SourceItem.create(
                kind=source_item.kind,
                original_value=source_item.original_value,
                normalized_value=source_item.normalized_value,
                external_id=source_item.external_id,
                telegram_chat_id=source_item.telegram_chat_id,
                telegram_message_id=source_item.telegram_message_id,
                telegram_media_group_id=source_item.telegram_media_group_id,
                request_id=request_id,
                title_hint=title or source_item.title_hint,
                metadata=source_item.metadata,
            ),
            text=content_text,
            title=title or source_item.title_hint,
            detected_language=str(metadata.get("detected_lang") or "").strip() or None,
            content_source=content_source,
            metadata=metadata,
        )
        return request_id, normalized_document, metadata

    def _extract_telegram_submission(
        self,
        *,
        message: Any,
        source_item: SourceItem,
    ) -> tuple[int | None, NormalizedSourceDocument, dict[str, Any]]:
        text = str(
            getattr(message, "text", None) or getattr(message, "caption", None) or ""
        ).strip()
        media = _build_telegram_media_assets(message)
        metadata = _build_telegram_metadata(message)
        if not text and not media:
            msg = "Telegram submission has neither text nor supported media metadata"
            raise ValueError(msg)

        text_blocks = []
        if source_item.title_hint:
            text_blocks.append(
                SourceTextBlock(
                    kind=ExtractedTextKind.TITLE,
                    text=source_item.title_hint,
                    position=0,
                )
            )
        if text:
            text_blocks.append(
                SourceTextBlock(
                    kind=(
                        ExtractedTextKind.CAPTION
                        if getattr(message, "caption", None)
                        else ExtractedTextKind.BODY
                    ),
                    text=text,
                    position=len(text_blocks),
                )
            )

        normalized_document = NormalizedSourceDocument(
            source_item_id=source_item.stable_id,
            source_kind=source_item.kind,
            title=source_item.title_hint,
            text=text,
            detected_language=None,
            text_blocks=text_blocks,
            media=media,
            metadata=metadata,
            provenance=SourceProvenance(
                source_item_id=source_item.stable_id,
                source_kind=source_item.kind,
                original_value=source_item.original_value,
                normalized_value=source_item.normalized_value,
                external_id=source_item.external_id,
                request_id=source_item.request_id,
                telegram_chat_id=source_item.telegram_chat_id,
                telegram_message_id=source_item.telegram_message_id,
                telegram_media_group_id=source_item.telegram_media_group_id,
                extraction_source="telegram_native",
                metadata=dict(source_item.metadata),
            ),
        )
        return source_item.request_id, normalized_document, metadata

    @staticmethod
    def _resolve_session_status(
        *,
        successful_count: int,
        failed_count: int,
        duplicate_count: int,
    ) -> AggregationSessionStatus:
        if successful_count > 0 and failed_count > 0:
            return AggregationSessionStatus.PARTIAL
        if failed_count > 0 and successful_count == 0 and duplicate_count == 0:
            return AggregationSessionStatus.FAILED
        return AggregationSessionStatus.COMPLETED


def _extract_title_from_metadata(metadata: dict[str, Any]) -> str | None:
    direct_title = str(metadata.get("title") or "").strip()
    if direct_title:
        return direct_title
    firecrawl_metadata = metadata.get("firecrawl_metadata")
    if isinstance(firecrawl_metadata, dict):
        title = str(firecrawl_metadata.get("title") or "").strip()
        if title:
            return title
    return None


def _build_telegram_metadata(message: Any) -> dict[str, Any]:
    chat = getattr(message, "chat", None)
    forward_from_chat = getattr(message, "forward_from_chat", None)
    return {
        "chat_id": _coerce_int(getattr(chat, "id", None)),
        "message_id": _coerce_int(getattr(message, "id", getattr(message, "message_id", None))),
        "media_group_id": getattr(message, "media_group_id", None),
        "forward_from_chat_id": _coerce_int(getattr(forward_from_chat, "id", None)),
        "forward_from_chat_title": getattr(forward_from_chat, "title", None),
        "forward_from_message_id": _coerce_int(getattr(message, "forward_from_message_id", None)),
    }


def _build_telegram_media_assets(message: Any) -> list[SourceMediaAsset]:
    assets: list[SourceMediaAsset] = []
    photo = getattr(message, "photo", None)
    if photo is not None:
        photo_items = photo if isinstance(photo, list) else [photo]
        for index, item in enumerate(photo_items):
            file_id = getattr(item, "file_id", None)
            if not file_id:
                continue
            assets.append(
                SourceMediaAsset(
                    kind=SourceMediaKind.IMAGE,
                    url=f"telegram://file/{file_id}",
                    position=index,
                    metadata={
                        "telegram_file_id": file_id,
                        "width": _coerce_int(getattr(item, "width", None)),
                        "height": _coerce_int(getattr(item, "height", None)),
                    },
                )
            )

    document = getattr(message, "document", None)
    if document is not None:
        file_id = getattr(document, "file_id", None)
        mime_type = getattr(document, "mime_type", None)
        if file_id:
            assets.append(
                SourceMediaAsset(
                    kind=_media_kind_for_mime(mime_type),
                    url=f"telegram://file/{file_id}",
                    position=len(assets),
                    mime_type=str(mime_type) if mime_type else None,
                    metadata={
                        "telegram_file_id": file_id,
                        "file_name": getattr(document, "file_name", None),
                    },
                )
            )

    video = getattr(message, "video", None)
    if video is not None:
        file_id = getattr(video, "file_id", None)
        if file_id:
            assets.append(
                SourceMediaAsset(
                    kind=SourceMediaKind.VIDEO,
                    url=f"telegram://file/{file_id}",
                    position=len(assets),
                    mime_type="video/mp4",
                    metadata={
                        "telegram_file_id": file_id,
                        "duration": _coerce_int(getattr(video, "duration", None)),
                    },
                )
            )

    return assets


def _media_kind_for_mime(mime_type: Any) -> SourceMediaKind:
    mime = str(mime_type or "").strip().lower()
    if mime.startswith("image/"):
        return SourceMediaKind.IMAGE
    if mime.startswith("video/"):
        return SourceMediaKind.VIDEO
    if mime.startswith("audio/"):
        return SourceMediaKind.AUDIO
    return SourceMediaKind.DOCUMENT


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


__all__ = [
    "MultiSourceExtractionAgent",
    "MultiSourceExtractionInput",
]
