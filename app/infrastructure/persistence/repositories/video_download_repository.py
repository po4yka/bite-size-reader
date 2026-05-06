"""SQLAlchemy implementation of the video download repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update

from app.db.models import VideoDownload, model_to_dict

if TYPE_CHECKING:
    from app.db.session import Database


class VideoDownloadRepositoryAdapter:
    """Adapter for video download operations."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def async_create_video_download(
        self, request_id: int, video_id: str, status: str = "pending"
    ) -> int:
        """Create a new video download record."""
        async with self._database.transaction() as session:
            download = VideoDownload(request_id=request_id, video_id=video_id, status=status)
            session.add(download)
            await session.flush()
            return download.id

    async def async_get_video_download_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Get video download by request ID."""
        async with self._database.session() as session:
            download = await session.scalar(
                select(VideoDownload).where(VideoDownload.request_id == request_id)
            )
            return model_to_dict(download)

    async def async_get_video_download_by_id(self, download_id: int) -> dict[str, Any] | None:
        """Get video download by ID."""
        async with self._database.session() as session:
            download = await session.get(VideoDownload, download_id)
            return model_to_dict(download)

    async def async_update_video_download_status(
        self,
        download_id: int,
        status: str,
        error_text: str | None = None,
        download_started_at: Any | None = None,
    ) -> None:
        """Update video download status."""
        update_data: dict[str, Any] = {"status": status}
        if error_text is not None:
            update_data["error_text"] = error_text
        if download_started_at is not None:
            update_data["download_started_at"] = download_started_at
        await self.async_update_video_download(download_id, **update_data)

    async def async_update_video_download(self, download_id: int, **kwargs: Any) -> None:
        """Update video download with arbitrary fields."""
        if not kwargs:
            return
        allowed_fields = set(VideoDownload.__mapper__.columns.keys()) - {"id"}
        update_values = {key: value for key, value in kwargs.items() if key in allowed_fields}
        if not update_values:
            return
        async with self._database.transaction() as session:
            await session.execute(
                update(VideoDownload).where(VideoDownload.id == download_id).values(**update_values)
            )
