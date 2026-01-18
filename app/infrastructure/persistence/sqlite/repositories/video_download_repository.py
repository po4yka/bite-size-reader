"""SQLite implementation of video download repository.

This adapter handles persistence for YouTube video download metadata and status.
"""

from __future__ import annotations

from typing import Any

from app.db.models import VideoDownload, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteVideoDownloadRepositoryAdapter(SqliteBaseRepository):
    """Adapter for video download operations."""

    async def async_create_video_download(
        self, request_id: int, video_id: str, status: str = "pending"
    ) -> int:
        """Create a new video download record."""

        def _create() -> int:
            download = VideoDownload.create(request_id=request_id, video_id=video_id, status=status)
            return download.id

        return await self._execute(_create, operation_name="create_video_download")

    async def async_get_video_download_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Get video download by request ID."""

        def _get() -> dict[str, Any] | None:
            try:
                download = VideoDownload.get(VideoDownload.request_id == request_id)
                return model_to_dict(download)
            except VideoDownload.DoesNotExist:
                return None

        return await self._execute(
            _get, operation_name="get_video_download_by_request", read_only=True
        )

    async def async_get_video_download_by_id(self, download_id: int) -> dict[str, Any] | None:
        """Get video download by ID."""

        def _get() -> dict[str, Any] | None:
            try:
                download = VideoDownload.get_by_id(download_id)
                return model_to_dict(download)
            except VideoDownload.DoesNotExist:
                return None

        return await self._execute(_get, operation_name="get_video_download_by_id", read_only=True)

    async def async_update_video_download_status(
        self,
        download_id: int,
        status: str,
        error_text: str | None = None,
        download_started_at: Any | None = None,
    ) -> None:
        """Update video download status."""

        def _update() -> None:
            update_data = {"status": status}
            if error_text is not None:
                update_data["error_text"] = error_text
            if download_started_at is not None:
                update_data["download_started_at"] = download_started_at

            VideoDownload.update(**update_data).where(VideoDownload.id == download_id).execute()

        await self._execute(_update, operation_name="update_video_download_status")

    async def async_update_video_download(self, download_id: int, **kwargs: Any) -> None:
        """Update video download with arbitrary fields."""

        def _update() -> None:
            VideoDownload.update(**kwargs).where(VideoDownload.id == download_id).execute()

        await self._execute(_update, operation_name="update_video_download")
