"""SQLAlchemy repository for attachment processing records."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update

from app.db.models import AttachmentProcessing

if TYPE_CHECKING:
    from app.db.session import Database


class AttachmentProcessingRepositoryAdapter:
    """Owns persistence for attachment extraction state."""

    def __init__(self, database: Database) -> None:
        self._database = database

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
        async with self._database.transaction() as session:
            session.add(
                AttachmentProcessing(
                    request_id=request_id,
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
            )

    async def async_update_processing(self, request_id: int, **fields: Any) -> bool:
        if not fields:
            async with self._database.session() as session:
                exists = await session.scalar(
                    select(AttachmentProcessing.id).where(
                        AttachmentProcessing.request_id == request_id
                    )
                )
                return exists is not None

        allowed_fields = set(AttachmentProcessing.__mapper__.columns.keys()) - {"id", "request_id"}
        update_values = {key: value for key, value in fields.items() if key in allowed_fields}
        if not update_values:
            return False

        async with self._database.transaction() as session:
            result = await session.execute(
                update(AttachmentProcessing)
                .where(AttachmentProcessing.request_id == request_id)
                .values(**update_values)
                .returning(AttachmentProcessing.id)
            )
            return result.scalar_one_or_none() is not None
