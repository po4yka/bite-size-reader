"""Tests for YouTube partial download cleanup on CancelledError.

Verifies that partial files are cleaned up even when a download is
cancelled (e.g. bot shutdown, user cancellation), and that successful
downloads are NOT cleaned up.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
    )
except ModuleNotFoundError:
    # Provide lightweight stand-ins when the optional dependency isn't installed.
    class NoTranscriptFound(Exception):  # type: ignore[no-redef]
        pass

    class TranscriptsDisabled(Exception):  # type: ignore[no-redef]
        pass

    class VideoUnavailable(Exception):  # type: ignore[no-redef]
        pass

    YouTubeTranscriptApi = MagicMock()  # type: ignore[misc]
    sys.modules["youtube_transcript_api"] = MagicMock(YouTubeTranscriptApi=YouTubeTranscriptApi)
    sys.modules["youtube_transcript_api._errors"] = MagicMock(
        NoTranscriptFound=NoTranscriptFound,
        TranscriptsDisabled=TranscriptsDisabled,
        VideoUnavailable=VideoUnavailable,
    )

sys.modules.setdefault("pydantic", MagicMock())
sys.modules.setdefault("pydantic_settings", MagicMock())
sys.modules.setdefault("peewee", MagicMock())
sys.modules.setdefault("playhouse", MagicMock())
sys.modules.setdefault("playhouse.sqlite_ext", MagicMock())

from app.adapters.youtube.youtube_downloader import YouTubeDownloader

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.config import AppConfig


class _StubYouTubeConfig:
    def __init__(self, storage_path: str) -> None:
        self.enabled = True
        self.storage_path = storage_path
        self.max_video_size_mb = 500
        self.max_storage_gb = 100
        self.auto_cleanup_enabled = False
        self.cleanup_after_days = 30
        self.preferred_quality = "1080p"
        self.subtitle_languages = ["en"]


def _make_downloader(tmp_path: Path) -> YouTubeDownloader:
    """Build a YouTubeDownloader with minimal mocking for cleanup tests."""
    cfg = MagicMock()
    cfg.youtube = _StubYouTubeConfig(str(tmp_path / "videos"))
    db = MagicMock()
    rf = MagicMock()
    rf.safe_reply = AsyncMock()
    rf.send_youtube_download_notification = AsyncMock()
    rf.send_youtube_download_complete_notification = AsyncMock()
    downloader = YouTubeDownloader(
        cfg=cast("AppConfig", cfg),
        db=db,
        response_formatter=cast("ResponseFormatter", rf),
        audit_func=lambda *a, **k: None,
    )

    # Mock repositories to avoid DB interaction
    downloader.request_repo = MagicMock()
    downloader.request_repo.async_get_request_by_dedupe_hash = AsyncMock(return_value=None)
    downloader.request_repo.async_create_request = AsyncMock(return_value=1)
    downloader.request_repo.async_update_request_status = AsyncMock()
    downloader.request_repo.async_update_request_lang_detected = AsyncMock()

    downloader.video_repo = MagicMock()
    downloader.video_repo.async_create_video_download = AsyncMock(return_value=10)
    downloader.video_repo.async_update_video_download = AsyncMock()
    downloader.video_repo.async_update_video_download_status = AsyncMock()
    downloader.video_repo.async_get_video_download_by_request = AsyncMock(return_value=None)

    return downloader


def _create_mock_message() -> MagicMock:
    message = MagicMock()
    message.chat.id = 1
    message.from_user.id = 1
    message.id = 100
    return message


class TestCancelledErrorCleansUpPartialFiles(unittest.IsolatedAsyncioTestCase):
    """CancelledError during download must still clean up partial files."""

    async def test_cancelled_error_removes_partial_files(self):
        """Partial files matching video_id pattern are removed on CancelledError."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            downloader = _make_downloader(tmp)
            video_id = "dQw4w9WgXcQ"

            # Pre-create the date directory and partial files that yt-dlp would create
            date_dir = downloader.storage_path / "20260204"
            date_dir = Path(str(date_dir))
            date_dir.mkdir(parents=True, exist_ok=True)

            partial_files = [
                date_dir / f"{video_id}_SomeTitle.mp4.part",
                date_dir / f"{video_id}_SomeTitle.m4a",
                date_dir / f"{video_id}_SomeTitle.mp4",
            ]
            for f in partial_files:
                f.write_bytes(b"\x00" * 128)

            # Also create a file from a DIFFERENT video -- it must survive
            unrelated = date_dir / "otherVid_Foo.mp4"
            unrelated.write_bytes(b"\x00" * 64)

            assert all(f.exists() for f in partial_files), "precondition: partial files exist"

            # Mock transcript extraction to succeed (so output_dir gets set)
            async def _mock_extract_transcript(vid, cid):
                return ("Some transcript", "en", False, "youtube-transcript-api")

            # Mock the yt-dlp download to raise CancelledError AFTER output_dir is set.
            # We do this by having asyncio.wait_for raise CancelledError.
            async def _mock_wait_for(coro, *, timeout=None):
                # The first wait_for in download_and_extract is the yt-dlp download
                # (line 284). We need to consume the coroutine to avoid warnings,
                # then raise CancelledError.
                try:
                    coro.close()
                except AttributeError:
                    pass
                raise asyncio.CancelledError()

            with (
                patch(
                    "app.adapters.youtube.youtube_downloader.extract_youtube_video_id",
                    return_value=video_id,
                ),
                patch(
                    "app.adapters.youtube.youtube_downloader.normalize_url",
                    return_value=f"https://youtube.com/watch?v={video_id}",
                ),
                patch(
                    "app.adapters.youtube.youtube_downloader.url_hash_sha256",
                    return_value="fakehash",
                ),
                patch.object(downloader, "_check_storage_limits", new_callable=AsyncMock),
                patch.object(
                    downloader,
                    "_extract_transcript_api",
                    side_effect=_mock_extract_transcript,
                ),
                patch(
                    "app.adapters.youtube.youtube_downloader.datetime",
                ) as mock_dt,
                patch(
                    "asyncio.wait_for",
                    side_effect=_mock_wait_for,
                ),
            ):
                # Make datetime.now().strftime() return the same date dir name
                mock_dt.now.return_value.strftime.return_value = "20260204"
                mock_dt.side_effect = lambda *a, **kw: MagicMock()

                message = _create_mock_message()

                with self.assertRaises(asyncio.CancelledError):
                    await downloader.download_and_extract(
                        message,
                        f"https://www.youtube.com/watch?v={video_id}",
                        "test-cid",
                    )

            # Partial files for video_id must be gone
            for f in partial_files:
                self.assertFalse(
                    f.exists(),
                    f"Expected partial file to be cleaned up: {f.name}",
                )

            # Unrelated file must still exist
            self.assertTrue(unrelated.exists(), "Unrelated file must not be removed")


class TestSuccessfulDownloadNotCleanedUp(unittest.IsolatedAsyncioTestCase):
    """A successful download must NOT have its files cleaned up."""

    async def test_successful_download_preserves_files(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            downloader = _make_downloader(tmp)
            video_id = "successVid"

            date_dir = Path(str(downloader.storage_path)) / "20260204"
            date_dir.mkdir(parents=True, exist_ok=True)

            # These files represent a completed download
            video_file = date_dir / f"{video_id}_Title.mp4"
            video_file.write_bytes(b"\x00" * 256)

            with (
                patch(
                    "app.adapters.youtube.youtube_downloader.extract_youtube_video_id",
                    return_value=video_id,
                ),
                patch(
                    "app.adapters.youtube.youtube_downloader.normalize_url",
                    return_value=f"https://youtube.com/watch?v={video_id}",
                ),
                patch(
                    "app.adapters.youtube.youtube_downloader.url_hash_sha256",
                    return_value="fakehash2",
                ),
                patch.object(downloader, "_check_storage_limits", new_callable=AsyncMock),
                patch.object(
                    downloader,
                    "_extract_transcript_api",
                    return_value=("Transcript text", "en", False, "youtube-transcript-api"),
                ),
                patch.object(
                    downloader,
                    "_download_video_sync",
                    return_value={
                        "video_file_path": str(video_file),
                        "title": "Title",
                        "channel": "Chan",
                        "channel_id": "UC1",
                        "duration": 60,
                        "resolution": "1080p",
                        "file_size": 256,
                        "upload_date": "20260204",
                        "view_count": 10,
                        "like_count": 1,
                        "vcodec": "h264",
                        "acodec": "aac",
                        "format_id": "137+140",
                        "subtitle_file_path": None,
                    },
                ),
                patch(
                    "asyncio.to_thread",
                    side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
                ),
                patch(
                    "app.adapters.youtube.youtube_downloader.datetime",
                ) as mock_dt,
            ):
                mock_dt.now.return_value.strftime.return_value = "20260204"

                message = _create_mock_message()
                result = await downloader.download_and_extract(
                    message,
                    f"https://www.youtube.com/watch?v={video_id}",
                    "test-cid",
                )

                # Should return successfully
                self.assertEqual(result[0], 1)  # req_id

            # Video file must still exist after successful download
            self.assertTrue(
                video_file.exists(),
                "Successful download files must NOT be cleaned up",
            )


class TestEmptyDateDirectoryCleanup(unittest.IsolatedAsyncioTestCase):
    """Empty date directories should be removed after partial file cleanup."""

    async def test_empty_directory_removed_after_cleanup(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            downloader = _make_downloader(tmp)
            video_id = "emptyDirVid"

            date_dir = Path(str(downloader.storage_path)) / "20260204"
            date_dir.mkdir(parents=True, exist_ok=True)

            # Only files from this video -- so after cleanup the directory should be empty
            partial = date_dir / f"{video_id}_Title.mp4.part"
            partial.write_bytes(b"\x00" * 64)

            async def _mock_extract_transcript(vid, cid):
                return ("Transcript", "en", False, "youtube-transcript-api")

            async def _mock_wait_for(coro, *, timeout=None):
                try:
                    coro.close()
                except AttributeError:
                    pass
                raise asyncio.CancelledError()

            with (
                patch(
                    "app.adapters.youtube.youtube_downloader.extract_youtube_video_id",
                    return_value=video_id,
                ),
                patch(
                    "app.adapters.youtube.youtube_downloader.normalize_url",
                    return_value=f"https://youtube.com/watch?v={video_id}",
                ),
                patch(
                    "app.adapters.youtube.youtube_downloader.url_hash_sha256",
                    return_value="fakehash3",
                ),
                patch.object(downloader, "_check_storage_limits", new_callable=AsyncMock),
                patch.object(
                    downloader,
                    "_extract_transcript_api",
                    side_effect=_mock_extract_transcript,
                ),
                patch(
                    "app.adapters.youtube.youtube_downloader.datetime",
                ) as mock_dt,
                patch(
                    "asyncio.wait_for",
                    side_effect=_mock_wait_for,
                ),
            ):
                mock_dt.now.return_value.strftime.return_value = "20260204"

                message = _create_mock_message()

                with self.assertRaises(asyncio.CancelledError):
                    await downloader.download_and_extract(
                        message,
                        f"https://www.youtube.com/watch?v={video_id}",
                        "test-cid",
                    )

            # Partial file must be gone
            self.assertFalse(partial.exists(), "Partial file must be cleaned up")

            # Empty date directory must also be gone
            self.assertFalse(
                date_dir.exists(),
                "Empty date directory should be removed after cleanup",
            )


if __name__ == "__main__":
    unittest.main()
