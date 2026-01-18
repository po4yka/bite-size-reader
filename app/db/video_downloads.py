"""Video download persistence helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.db.models import VideoDownload

if TYPE_CHECKING:
    import logging


class VideoDownloadManager:
    """Manage video download records."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def create_video_download(self, request_id: int, video_id: str, status: str = "pending") -> int:
        """Create a new video download record."""
        download = VideoDownload.create(request_id=request_id, video_id=video_id, status=status)
        self._logger.info(
            "video_download_created", extra={"download_id": download.id, "video_id": video_id}
        )
        return download.id

    def get_video_download_by_request(self, request_id: int):
        """Get video download by request ID."""
        try:
            return VideoDownload.get(VideoDownload.request_id == request_id)
        except VideoDownload.DoesNotExist:
            return None

    def get_video_download_by_id(self, download_id: int):
        """Get video download by ID."""
        try:
            return VideoDownload.get_by_id(download_id)
        except VideoDownload.DoesNotExist:
            return None

    def update_video_download_status(
        self,
        download_id: int,
        status: str,
        error_text: str | None = None,
        download_started_at=None,
    ) -> None:
        """Update video download status."""
        update_data = {"status": status}
        if error_text is not None:
            update_data["error_text"] = error_text
        if download_started_at is not None:
            update_data["download_started_at"] = download_started_at

        VideoDownload.update(**update_data).where(VideoDownload.id == download_id).execute()
        self._logger.debug(
            "video_download_status_updated", extra={"download_id": download_id, "status": status}
        )

    def update_video_download(self, download_id: int, **kwargs: Any) -> None:
        """Update video download fields."""
        VideoDownload.update(**kwargs).where(VideoDownload.id == download_id).execute()
        self._logger.debug("video_download_updated", extra={"download_id": download_id})
