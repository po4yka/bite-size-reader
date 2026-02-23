"""Embedding, audit-log, and video-download operations for Database facade."""
# mypy: disable-error-code=attr-defined

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

import peewee

from app.core.time_utils import UTC
from app.db.models import AuditLog, SummaryEmbedding

JSONValue = Mapping[str, Any] | list[Any] | tuple[Any, ...] | str | None


class DatabaseEmbeddingMediaOpsMixin:
    """Embedding/audit/video delegate operations."""

    def create_or_update_summary_embedding(
        self,
        summary_id: int,
        embedding_blob: bytes,
        model_name: str,
        model_version: str,
        dimensions: int,
        language: str | None = None,
    ) -> None:
        """Store or update embedding for a summary."""
        try:
            SummaryEmbedding.create(
                summary=summary_id,
                embedding_blob=embedding_blob,
                model_name=model_name,
                model_version=model_version,
                dimensions=dimensions,
                language=language,
            )
        except peewee.IntegrityError:
            SummaryEmbedding.update(
                {
                    SummaryEmbedding.embedding_blob: embedding_blob,
                    SummaryEmbedding.model_name: model_name,
                    SummaryEmbedding.model_version: model_version,
                    SummaryEmbedding.dimensions: dimensions,
                    SummaryEmbedding.language: language,
                    SummaryEmbedding.created_at: dt.datetime.now(UTC),
                }
            ).where(SummaryEmbedding.summary == summary_id).execute()

    async def async_create_or_update_summary_embedding(
        self,
        summary_id: int,
        embedding_blob: bytes,
        model_name: str,
        model_version: str,
        dimensions: int,
        language: str | None = None,
    ) -> None:
        """Asynchronously store or update embedding for a summary."""
        await self._safe_db_operation(
            self.create_or_update_summary_embedding,
            summary_id=summary_id,
            embedding_blob=embedding_blob,
            model_name=model_name,
            model_version=model_version,
            dimensions=dimensions,
            language=language,
            operation_name="create_or_update_summary_embedding",
        )

    def get_summary_embedding(self, summary_id: int) -> dict[str, Any] | None:
        """Retrieve embedding for a summary."""
        embedding = SummaryEmbedding.get_or_none(SummaryEmbedding.summary == summary_id)
        if embedding is None:
            return None
        return {
            "embedding_blob": embedding.embedding_blob,
            "model_name": embedding.model_name,
            "model_version": embedding.model_version,
            "dimensions": embedding.dimensions,
            "language": embedding.language,
            "created_at": embedding.created_at,
        }

    async def async_get_summary_embedding(self, summary_id: int) -> dict[str, Any] | None:
        """Asynchronously retrieve embedding for a summary."""
        return await self._safe_db_operation(
            self.get_summary_embedding,
            summary_id=summary_id,
            operation_name="get_summary_embedding",
            read_only=True,
        )

    def insert_audit_log(
        self,
        *,
        level: str,
        event: str,
        details_json: JSONValue = None,
    ) -> int:
        entry = AuditLog.create(
            level=level,
            event=event,
            details_json=self._prepare_json_payload(details_json),
        )
        return entry.id

    def create_video_download(self, request_id: int, video_id: str, status: str = "pending") -> int:
        """Create a new video download record."""
        return self._video_downloads.create_video_download(request_id, video_id, status=status)

    def get_video_download_by_request(self, request_id: int):
        """Get video download by request ID."""
        return self._video_downloads.get_video_download_by_request(request_id)

    def get_video_download_by_id(self, download_id: int):
        """Get video download by ID."""
        return self._video_downloads.get_video_download_by_id(download_id)

    def update_video_download_status(
        self,
        download_id: int,
        status: str,
        error_text: str | None = None,
        download_started_at=None,
    ) -> None:
        """Update video download status."""
        self._video_downloads.update_video_download_status(
            download_id,
            status,
            error_text=error_text,
            download_started_at=download_started_at,
        )

    def update_video_download(self, download_id: int, **kwargs) -> None:
        """Update video download with arbitrary fields."""
        self._video_downloads.update_video_download(download_id, **kwargs)
