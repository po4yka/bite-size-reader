"""Persistence helpers for attachment processing."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from app.adapters.attachment._attachment_shared import coerce_int
from app.db.user_interactions import async_safe_update_user_interaction
from app.domain.models.request import RequestStatus

if TYPE_CHECKING:
    from app.adapters.attachment._attachment_shared import AttachmentProcessorContext


class AttachmentPersistenceService:
    """Encapsulates request and attachment record persistence."""

    def __init__(self, context: AttachmentProcessorContext) -> None:
        self._context = context

    async def create_request(
        self,
        message: Any,
        correlation_id: str | None,
        file_type: str,
    ) -> int:
        """Create a request record for the attachment."""
        chat_obj = getattr(message, "chat", None)
        chat_id = coerce_int(getattr(chat_obj, "id", None) if chat_obj else None)
        from_user = getattr(message, "from_user", None)
        user_id = coerce_int(getattr(from_user, "id", None) if from_user else None)
        msg_id = coerce_int(getattr(message, "id", getattr(message, "message_id", None)))

        return await self._context.request_repo.async_create_request(
            type_=file_type,
            status=RequestStatus.PENDING,
            correlation_id=correlation_id,
            chat_id=chat_id,
            user_id=user_id,
            input_message_id=msg_id,
            content_text=getattr(message, "caption", None),
        )

    async def create_attachment_record(
        self,
        *,
        req_id: int,
        file_type: str,
        mime_type: str | None,
        file_name: str | None,
        file_size: int | None,
    ) -> None:
        """Create an attachment processing record."""
        from app.db.models import AttachmentProcessing

        def _create() -> None:
            AttachmentProcessing.create(
                request=req_id,
                file_type=file_type,
                mime_type=mime_type,
                file_name=file_name,
                file_size_bytes=file_size,
                status="processing",
            )

        await asyncio.to_thread(_create)

    async def update_attachment_status(
        self,
        req_id: int,
        status: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Update the attachment processing status."""
        from app.db.models import AttachmentProcessing

        def _update() -> None:
            try:
                record = AttachmentProcessing.get(AttachmentProcessing.request == req_id)
                record.status = status
                if result:
                    record.extracted_text_length = len(result.get("tldr", ""))
                record.save()
            except AttachmentProcessing.DoesNotExist:
                self._context.logger.debug(
                    "attachment_record_not_found",
                    extra={"request_id": req_id},
                )
                AttachmentProcessing.create(
                    request=req_id,
                    status=status,
                    extracted_text_length=len(result.get("tldr", "")) if result else None,
                )

        await asyncio.to_thread(_update)

    async def update_pdf_metadata(self, req_id: int, pdf_content: Any) -> None:
        """Update attachment metadata after PDF extraction."""
        from app.db.models import AttachmentProcessing

        def _update() -> None:
            try:
                record = AttachmentProcessing.get(AttachmentProcessing.request == req_id)
                record.page_count = pdf_content.page_count
                record.extracted_text_length = len(pdf_content.text)
                record.vision_used = bool(pdf_content.image_pages)
                record.vision_pages_count = (
                    len(pdf_content.image_pages) if pdf_content.image_pages else None
                )
                record.processing_method = _determine_processing_method(pdf_content)
                record.save()
            except AttachmentProcessing.DoesNotExist:
                self._context.logger.debug(
                    "attachment_record_not_found_pdf",
                    extra={"request_id": req_id},
                )
                AttachmentProcessing.create(
                    request=req_id,
                    status="processing",
                    page_count=pdf_content.page_count,
                    extracted_text_length=len(pdf_content.text),
                    vision_used=bool(pdf_content.image_pages),
                    vision_pages_count=len(pdf_content.image_pages)
                    if pdf_content.image_pages
                    else None,
                    processing_method=_determine_processing_method(pdf_content),
                )

        await asyncio.to_thread(_update)

    async def send_attachment_result(
        self,
        message: Any,
        result: dict[str, Any],
        req_id: int,
        interaction_id: int | None,
    ) -> None:
        """Send the summary and persist interaction metadata."""
        await self._context.response_formatter.send_forward_summary_response(
            message,
            result,
            summary_id=f"req:{req_id}",
        )
        if interaction_id:
            await async_safe_update_user_interaction(
                self._context.user_repo,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="summary",
                request_id=req_id,
                logger_=self._context.logger,
            )


def _determine_processing_method(pdf_content: Any) -> str:
    if pdf_content.image_pages and pdf_content.text.strip():
        return "hybrid"
    if pdf_content.is_scanned:
        return "vision"
    return "text_extraction"
