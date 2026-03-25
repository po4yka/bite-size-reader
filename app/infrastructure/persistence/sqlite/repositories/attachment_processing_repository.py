"""SQLite repository for attachment processing records."""

from __future__ import annotations

from typing import Any

from app.db.models import AttachmentProcessing
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteAttachmentProcessingRepositoryAdapter(SqliteBaseRepository):
    """Owns persistence for attachment extraction state."""

    async def async_create_processing(
        self,
        *,
        request_id: int,
        file_type: str | None = None,
        mime_type: str | None = None,
        file_name: str | None = None,
        file_size_bytes: int | None = None,
        status: str = "processing",
        extracted_text_length: int | None = None,
        page_count: int | None = None,
        vision_used: bool | None = None,
        vision_pages_count: int | None = None,
        processing_method: str | None = None,
    ) -> None:
        def _insert() -> None:
            AttachmentProcessing.create(
                request=request_id,
                file_type=file_type,
                mime_type=mime_type,
                file_name=file_name,
                file_size_bytes=file_size_bytes,
                status=status,
                extracted_text_length=extracted_text_length,
                page_count=page_count,
                vision_used=vision_used,
                vision_pages_count=vision_pages_count,
                processing_method=processing_method,
            )

        await self._execute(_insert, operation_name="create_attachment_processing")

    async def async_update_processing(self, request_id: int, **fields: Any) -> bool:
        def _update() -> bool:
            record = AttachmentProcessing.get_or_none(AttachmentProcessing.request == request_id)
            if record is None:
                return False
            for key, value in fields.items():
                setattr(record, key, value)
            record.save()
            return True

        return await self._execute(_update, operation_name="update_attachment_processing")
