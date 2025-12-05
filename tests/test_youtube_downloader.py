import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.modules.setdefault("pydantic", MagicMock())
sys.modules.setdefault("pydantic_settings", MagicMock())
sys.modules.setdefault("peewee", MagicMock())
sys.modules.setdefault("playhouse", MagicMock())
sys.modules.setdefault("playhouse.sqlite_ext", MagicMock())

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

    YouTubeTranscriptApi = MagicMock()
    sys.modules["youtube_transcript_api"] = MagicMock(YouTubeTranscriptApi=YouTubeTranscriptApi)
    sys.modules["youtube_transcript_api._errors"] = MagicMock(
        NoTranscriptFound=NoTranscriptFound,
        TranscriptsDisabled=TranscriptsDisabled,
        VideoUnavailable=VideoUnavailable,
    )

import yt_dlp  # noqa: E402

from app.adapters.youtube.youtube_downloader import YouTubeDownloader  # noqa: E402


class TestYouTubeDownloader(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.cfg = MagicMock()
        self.cfg.youtube.storage_path = "/tmp/test_videos"
        self.cfg.youtube.max_video_size_mb = 500
        self.cfg.youtube.max_storage_gb = 100
        self.cfg.youtube.preferred_quality = "1080p"
        self.cfg.youtube.subtitle_languages = ["en", "ru"]
        self.cfg.youtube.auto_cleanup_enabled = True

        self.db = MagicMock()
        self.db.async_get_request_by_dedupe_hash = AsyncMock(return_value=None)
        self.db.get_video_download_by_request = MagicMock(return_value=None)
        self.db.create_request = MagicMock(return_value=123)
        self.db.create_video_download = MagicMock(return_value=456)
        self.db.update_video_download_status = MagicMock()
        self.db.update_video_download = MagicMock()
        self.db.update_request_status = MagicMock()
        self.db.update_request_lang_detected = MagicMock()

        self.response_formatter = MagicMock()
        self.response_formatter.send_youtube_download_notification = AsyncMock()
        self.response_formatter.send_youtube_download_complete_notification = AsyncMock()

        self.audit_func = MagicMock()

        with patch("pathlib.Path.mkdir"):
            self.downloader = YouTubeDownloader(
                cfg=self.cfg,
                db=self.db,
                response_formatter=self.response_formatter,
                audit_func=self.audit_func,
            )

    def _create_mock_message(self, chat_id: int = 1, user_id: int = 1, msg_id: int = 100):
        message = MagicMock()
        message.chat.id = chat_id
        message.from_user.id = user_id
        message.id = msg_id
        return message


class TestURLParsing(TestYouTubeDownloader):
    """Test URL parsing and video ID extraction."""

    @patch("app.adapters.youtube.youtube_downloader.extract_youtube_video_id")
    async def test_extract_video_id_standard_watch_url(self, mock_extract):
        mock_extract.return_value = "dQw4w9WgXcQ"
        message = self._create_mock_message()

        with patch.object(
            self.downloader, "_extract_transcript_api", return_value=("", "en", False)
        ):
            with patch.object(
                self.downloader,
                "_download_video_sync",
                return_value={
                    "video_file_path": "/tmp/video.mp4",
                    "title": "Test",
                    "resolution": "1080p",
                    "file_size": 1024,
                },
            ):
                with patch(
                    "asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)
                ):
                    await self.downloader.download_and_extract(
                        message, "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "cid"
                    )

        mock_extract.assert_called()

    @patch("app.adapters.youtube.youtube_downloader.extract_youtube_video_id")
    async def test_extract_video_id_shorts_url(self, mock_extract):
        mock_extract.return_value = "abc123XYZ"
        message = self._create_mock_message()

        with patch.object(
            self.downloader, "_extract_transcript_api", return_value=("", "en", False)
        ):
            with patch.object(
                self.downloader,
                "_download_video_sync",
                return_value={
                    "video_file_path": "/tmp/video.mp4",
                    "title": "Test",
                    "resolution": "1080p",
                    "file_size": 1024,
                },
            ):
                with patch(
                    "asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)
                ):
                    await self.downloader.download_and_extract(
                        message, "https://www.youtube.com/shorts/abc123XYZ", "cid"
                    )

        mock_extract.assert_called()

    @patch("app.adapters.youtube.youtube_downloader.extract_youtube_video_id")
    async def test_invalid_url_raises_error(self, mock_extract):
        mock_extract.return_value = None
        message = self._create_mock_message()

        with self.assertRaises(ValueError) as ctx:
            await self.downloader.download_and_extract(
                message, "https://not-youtube.com/video", "cid"
            )

        self.assertIn("Invalid YouTube URL", str(ctx.exception))

    @patch("app.adapters.youtube.youtube_downloader.extract_youtube_video_id")
    async def test_url_with_query_params(self, mock_extract):
        mock_extract.return_value = "videoID123"
        message = self._create_mock_message()

        with patch.object(
            self.downloader, "_extract_transcript_api", return_value=("", "en", False)
        ):
            with patch.object(
                self.downloader,
                "_download_video_sync",
                return_value={
                    "video_file_path": "/tmp/video.mp4",
                    "title": "Test",
                    "resolution": "1080p",
                    "file_size": 1024,
                },
            ):
                with patch(
                    "asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)
                ):
                    await self.downloader.download_and_extract(
                        message, "https://www.youtube.com/watch?v=videoID123&feature=share", "cid"
                    )

        mock_extract.assert_called()


class TestTranscriptExtraction(TestYouTubeDownloader):
    """Test transcript extraction with youtube-transcript-api."""

    @patch("app.adapters.youtube.youtube_downloader.YouTubeTranscriptApi")
    async def test_successful_manual_transcript_extraction(self, mock_api_class):
        transcript_data = [
            {"text": "Hello", "start": 0.0, "duration": 1.0},
            {"text": "World", "start": 1.0, "duration": 1.0},
        ]

        mock_transcript = MagicMock()
        mock_transcript.language_code = "en"
        mock_transcript.fetch.return_value = transcript_data

        mock_transcript_list = MagicMock()
        mock_transcript_list.find_transcript.return_value = mock_transcript

        mock_api_class.list_transcripts.return_value = mock_transcript_list

        text, lang, auto = await self.downloader._extract_transcript_api("test_video", "cid")

        self.assertEqual(text, "Hello World")
        self.assertEqual(lang, "en")
        self.assertFalse(auto)

    @patch("app.adapters.youtube.youtube_downloader.YouTubeTranscriptApi")
    async def test_fallback_to_auto_generated_transcript(self, mock_api_class):
        transcript_data = [
            {"text": "Auto generated", "start": 0.0, "duration": 1.0},
        ]

        mock_transcript = MagicMock()
        mock_transcript.language_code = "en"
        mock_transcript.fetch.return_value = transcript_data

        mock_transcript_list = MagicMock()
        mock_transcript_list.find_transcript.side_effect = NoTranscriptFound(
            "test_video", ["en"], None
        )
        mock_transcript_list.find_generated_transcript.return_value = mock_transcript

        mock_api_class.list_transcripts.return_value = mock_transcript_list

        text, lang, auto = await self.downloader._extract_transcript_api("test_video", "cid")

        self.assertEqual(text, "Auto generated")
        self.assertEqual(lang, "en")
        self.assertTrue(auto)

    @patch("app.adapters.youtube.youtube_downloader.YouTubeTranscriptApi")
    @patch("asyncio.to_thread")
    async def test_no_transcript_available(self, mock_to_thread, mock_api):
        mock_transcript_list = MagicMock()
        mock_transcript_list.find_transcript.side_effect = NoTranscriptFound(
            "test_video", ["en"], None
        )
        mock_transcript_list.find_generated_transcript.side_effect = NoTranscriptFound(
            "test_video", ["en"], None
        )

        async def mock_thread_fn(fn, *args):
            if fn.__name__ == "list_transcripts":
                return mock_transcript_list
            return fn(*args)

        mock_to_thread.side_effect = mock_thread_fn

        text, lang, auto = await self.downloader._extract_transcript_api("test_video", "cid")

        self.assertEqual(text, "")
        self.assertEqual(lang, "en")
        self.assertFalse(auto)

    @patch("app.adapters.youtube.youtube_downloader.YouTubeTranscriptApi")
    @patch("asyncio.to_thread")
    async def test_transcripts_disabled(self, mock_to_thread, mock_api):
        mock_transcript_list = MagicMock()
        mock_transcript_list.find_transcript.side_effect = TranscriptsDisabled("test_video")

        async def mock_thread_fn(fn, *args):
            if fn.__name__ == "list_transcripts":
                return mock_transcript_list
            return fn(*args)

        mock_to_thread.side_effect = mock_thread_fn

        text, lang, auto = await self.downloader._extract_transcript_api("test_video", "cid")

        self.assertEqual(text, "")
        self.assertEqual(lang, "en")
        self.assertFalse(auto)

    @patch("app.adapters.youtube.youtube_downloader.YouTubeTranscriptApi")
    async def test_video_unavailable(self, mock_api_class):
        mock_api_class.list_transcripts.side_effect = VideoUnavailable("test_video")

        with self.assertRaises(ValueError) as ctx:
            await self.downloader._extract_transcript_api("test_video", "cid")

        self.assertIn("unavailable", str(ctx.exception))

    @patch("app.adapters.youtube.youtube_downloader.YouTubeTranscriptApi")
    async def test_language_preference_handling(self, mock_api_class):
        transcript_data = [{"text": "English text", "start": 0.0, "duration": 1.0}]

        mock_transcript_en = MagicMock()
        mock_transcript_en.language_code = "en"
        mock_transcript_en.fetch.return_value = transcript_data

        mock_transcript_list = MagicMock()

        def find_transcript_side_effect(langs):
            if "en" in langs:
                return mock_transcript_en
            raise NoTranscriptFound("test_video", langs, None)

        mock_transcript_list.find_transcript.side_effect = find_transcript_side_effect

        mock_api_class.list_transcripts.return_value = mock_transcript_list

        text, lang, auto = await self.downloader._extract_transcript_api("test_video", "cid")

        self.assertEqual(text, "English text")
        self.assertEqual(lang, "en")
        self.assertFalse(auto)


class TestVideoDownload(TestYouTubeDownloader):
    """Test video download with yt-dlp."""

    def test_successful_video_download(self):
        mock_info = {
            "id": "test_video",
            "title": "Test Video",
            "uploader": "Test Channel",
            "channel_id": "UC123",
            "duration": 120,
            "height": 1080,
            "upload_date": "20250101",
            "view_count": 1000,
            "like_count": 100,
            "vcodec": "h264",
            "acodec": "aac",
            "format_id": "137+140",
            "filesize": 10485760,
        }

        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        mock_ydl.download.return_value = None
        mock_ydl.prepare_filename.return_value = "/tmp/test_video.mp4"
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=None)

        def path_exists_side_effect(self):
            # Only the video file exists, not the metadata or subtitle files
            return str(self).endswith(".mp4")

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            with patch("pathlib.Path.exists", path_exists_side_effect):
                with patch("pathlib.Path.stat") as mock_stat:
                    mock_stat.return_value.st_size = 10485760

                    result = self.downloader._download_video_sync(
                        "https://www.youtube.com/watch?v=test_video",
                        self.downloader._get_ydl_opts("test_video", Path("/tmp")),
                        456,
                        self._create_mock_message(),
                        False,
                        "cid",
                    )

        self.assertEqual(result["title"], "Test Video")
        self.assertEqual(result["resolution"], "1080p")
        self.assertEqual(result["file_size"], 10485760)

    def test_quality_selection_1080p(self):
        ydl_opts = self.downloader._get_ydl_opts("test_video", Path("/tmp"))

        self.assertIn("bestvideo[height<=1080]", ydl_opts["format"])
        self.assertEqual(ydl_opts["merge_output_format"], "mp4")

    def test_quality_selection_720p(self):
        self.cfg.youtube.preferred_quality = "720p"

        with patch("pathlib.Path.mkdir"):
            downloader = YouTubeDownloader(
                cfg=self.cfg,
                db=self.db,
                response_formatter=self.response_formatter,
                audit_func=self.audit_func,
            )

        ydl_opts = downloader._get_ydl_opts("test_video", Path("/tmp"))

        self.assertIn("bestvideo[height<=720]", ydl_opts["format"])

    def test_storage_path_organization(self):
        video_id = "test123"
        output_path = Path("/tmp/videos")

        ydl_opts = self.downloader._get_ydl_opts(video_id, output_path)

        self.assertIn(video_id, ydl_opts["outtmpl"])
        self.assertIn(str(output_path), ydl_opts["outtmpl"])

    def test_deduplication_existing_request(self):
        self.db.async_get_request_by_dedupe_hash = AsyncMock(
            return_value={"id": 789, "status": "ok"}
        )

        existing_download = MagicMock()
        existing_download.status = "completed"
        existing_download.transcript_text = "Existing transcript"
        existing_download.transcript_source = "cached"
        existing_download.subtitle_language = "en"
        existing_download.video_id = "test_video"
        existing_download.title = "Test"
        existing_download.channel = "Channel"
        existing_download.channel_id = "UC123"
        existing_download.duration_sec = 120
        existing_download.resolution = "1080p"
        existing_download.file_size_bytes = 1024
        existing_download.upload_date = "20250101"
        existing_download.view_count = 1000
        existing_download.like_count = 100
        existing_download.video_file_path = "/tmp/video.mp4"
        existing_download.subtitle_file_path = None
        existing_download.thumbnail_file_path = None

        self.db.get_video_download_by_request = MagicMock(return_value=existing_download)

        message = self._create_mock_message()

        with patch(
            "app.adapters.youtube.youtube_downloader.extract_youtube_video_id",
            return_value="test_video",
        ):
            with patch(
                "app.adapters.youtube.youtube_downloader.normalize_url",
                return_value="https://youtube.com/watch?v=test_video",
            ):
                with patch(
                    "app.adapters.youtube.youtube_downloader.url_hash_sha256", return_value="abc123"
                ):
                    with patch.object(self.downloader, "_check_storage_limits", return_value=None):

                        async def run_test():
                            (
                                req_id,
                                transcript,
                                source,
                                _lang,
                                _metadata,
                            ) = await self.downloader.download_and_extract(
                                message, "https://www.youtube.com/watch?v=test_video", "cid"
                            )

                            self.assertEqual(req_id, 789)
                            self.assertEqual(transcript, "Existing transcript")
                            self.assertEqual(source, "cached")

                        import asyncio

                        asyncio.run(run_test())


class TestErrorHandling(TestYouTubeDownloader):
    """Test error handling for various failure scenarios."""

    def _create_mock_ydl_with_context(self):
        """Helper to create mock YDL with context manager support."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=None)
        return mock_ydl

    def test_age_restricted_video_error(self):
        mock_ydl = self._create_mock_ydl_with_context()
        mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError(
            "Sign in to confirm your age"
        )

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            with self.assertRaises(ValueError) as ctx:
                self.downloader._download_video_sync(
                    "https://www.youtube.com/watch?v=age_restricted",
                    {},
                    456,
                    self._create_mock_message(),
                    False,
                    "cid",
                )

            self.assertIn("age-restricted", str(ctx.exception))

    def test_geo_blocked_video_error(self):
        mock_ydl = self._create_mock_ydl_with_context()
        mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError(
            "Video not available in your country"
        )

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            with self.assertRaises(ValueError) as ctx:
                self.downloader._download_video_sync(
                    "https://www.youtube.com/watch?v=geo_blocked",
                    {},
                    456,
                    self._create_mock_message(),
                    False,
                    "cid",
                )

            self.assertIn("geo-blocked", str(ctx.exception))

    def test_private_video_error(self):
        mock_ydl = self._create_mock_ydl_with_context()
        mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError("Private video")

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            with self.assertRaises(ValueError) as ctx:
                self.downloader._download_video_sync(
                    "https://www.youtube.com/watch?v=private",
                    {},
                    456,
                    self._create_mock_message(),
                    False,
                    "cid",
                )

            self.assertIn("private", str(ctx.exception))

    def test_rate_limit_error(self):
        mock_ydl = self._create_mock_ydl_with_context()
        mock_ydl.extract_info.return_value = {"id": "test", "filesize": 1024}
        mock_ydl.download.side_effect = yt_dlp.utils.DownloadError("HTTP Error 429")

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            with self.assertRaises(ValueError) as ctx:
                self.downloader._download_video_sync(
                    "https://www.youtube.com/watch?v=rate_limited",
                    {},
                    456,
                    self._create_mock_message(),
                    False,
                    "cid",
                )

            self.assertIn("rate limit", str(ctx.exception))

    def test_network_timeout_error(self):
        mock_ydl = self._create_mock_ydl_with_context()
        mock_ydl.extract_info.return_value = {"id": "test", "filesize": 1024}
        mock_ydl.download.side_effect = yt_dlp.utils.DownloadError("Connection timed out")

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            with self.assertRaises(ValueError) as ctx:
                self.downloader._download_video_sync(
                    "https://www.youtube.com/watch?v=timeout",
                    {},
                    456,
                    self._create_mock_message(),
                    False,
                    "cid",
                )

            self.assertIn("timed out", str(ctx.exception))

    def test_video_not_found_error(self):
        mock_ydl = self._create_mock_ydl_with_context()
        mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError("HTTP Error 404")

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            with self.assertRaises(ValueError) as ctx:
                self.downloader._download_video_sync(
                    "https://www.youtube.com/watch?v=notfound",
                    {},
                    456,
                    self._create_mock_message(),
                    False,
                    "cid",
                )

            # Check for either "not found" or "Failed to extract" (both are acceptable error messages)
            error_msg = str(ctx.exception).lower()
            self.assertTrue("not found" in error_msg or "failed to extract" in error_msg)

    def test_invalid_video_id_error(self):
        with patch(
            "app.adapters.youtube.youtube_downloader.extract_youtube_video_id", return_value=None
        ):
            message = self._create_mock_message()

            async def run_test():
                with self.assertRaises(ValueError) as ctx:
                    await self.downloader.download_and_extract(
                        message, "https://example.com/not-youtube", "cid"
                    )

                self.assertIn("Invalid YouTube URL", str(ctx.exception))

            import asyncio

            asyncio.run(run_test())


class TestStorageManagement(TestYouTubeDownloader):
    """Test storage management features."""

    def test_max_video_size_enforcement(self):
        mock_info = {"id": "test", "filesize": 600 * 1024 * 1024}  # 600MB
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=None)

        self.cfg.youtube.max_video_size_mb = 500

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            with self.assertRaises(ValueError) as ctx:
                self.downloader._download_video_sync(
                    "https://www.youtube.com/watch?v=toobig",
                    self.downloader._get_ydl_opts("test", Path("/tmp")),
                    456,
                    self._create_mock_message(),
                    False,
                    "cid",
                )

            self.assertIn("too large", str(ctx.exception))

    def test_storage_usage_calculation(self):
        with patch("pathlib.Path.rglob") as mock_rglob:
            mock_file1 = MagicMock()
            mock_file1.is_file.return_value = True
            mock_file1.stat.return_value.st_size = 100 * 1024 * 1024

            mock_file2 = MagicMock()
            mock_file2.is_file.return_value = True
            mock_file2.stat.return_value.st_size = 200 * 1024 * 1024

            mock_rglob.return_value = [mock_file1, mock_file2]

            usage = self.downloader._calculate_storage_usage()

            self.assertEqual(usage, 300 * 1024 * 1024)

    async def test_storage_limit_check_warning(self):
        self.cfg.youtube.max_storage_gb = 1

        with patch.object(
            self.downloader, "_calculate_storage_usage", return_value=950 * 1024 * 1024
        ):
            await self.downloader._check_storage_limits()

        self.cfg.youtube.auto_cleanup_enabled = True

        with patch.object(
            self.downloader, "_calculate_storage_usage", return_value=950 * 1024 * 1024
        ):
            await self.downloader._check_storage_limits()


class TestMetadataExtraction(TestYouTubeDownloader):
    """Test metadata extraction and database persistence."""

    def test_metadata_extraction_from_info(self):
        mock_info = {
            "id": "abc123",
            "title": "Test Video Title",
            "uploader": "Test Channel",
            "channel_id": "UC123456",
            "duration": 300,
            "height": 1080,
            "upload_date": "20250101",
            "view_count": 10000,
            "like_count": 500,
            "vcodec": "h264",
            "acodec": "aac",
            "format_id": "137+140",
            "filesize": 50 * 1024 * 1024,
        }

        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        mock_ydl.download.return_value = None
        mock_ydl.prepare_filename.return_value = "/tmp/abc123_Test Video Title.mp4"
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=None)

        def path_exists_side_effect(self):
            # Only the video file exists, not the metadata or subtitle files
            return str(self).endswith(".mp4")

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            with patch("pathlib.Path.exists", path_exists_side_effect):
                with patch("pathlib.Path.stat") as mock_stat:
                    mock_stat.return_value.st_size = 50 * 1024 * 1024

                    result = self.downloader._download_video_sync(
                        "https://www.youtube.com/watch?v=abc123",
                        self.downloader._get_ydl_opts("abc123", Path("/tmp")),
                        456,
                        self._create_mock_message(),
                        False,
                        "cid",
                    )

        self.assertEqual(result["video_id"], "abc123")
        self.assertEqual(result["title"], "Test Video Title")
        self.assertEqual(result["channel"], "Test Channel")
        self.assertEqual(result["channel_id"], "UC123456")
        self.assertEqual(result["duration"], 300)
        self.assertEqual(result["resolution"], "1080p")
        self.assertEqual(result["view_count"], 10000)
        self.assertEqual(result["like_count"], 500)
        self.assertEqual(result["vcodec"], "h264")
        self.assertEqual(result["acodec"], "aac")
        self.assertEqual(result["format_id"], "137+140")

    @patch(
        "app.adapters.youtube.youtube_downloader.extract_youtube_video_id",
        return_value="test_video",
    )
    @patch("app.adapters.youtube.youtube_downloader.normalize_url")
    @patch("app.adapters.youtube.youtube_downloader.url_hash_sha256")
    async def test_database_persistence(self, mock_hash, mock_normalize, mock_extract):
        mock_normalize.return_value = "https://youtube.com/watch?v=test_video"
        mock_hash.return_value = "hash123"

        message = self._create_mock_message()

        with patch.object(
            self.downloader,
            "_extract_transcript_api",
            return_value=("Test transcript", "en", False),
        ):
            with patch.object(
                self.downloader,
                "_download_video_sync",
                return_value={
                    "video_file_path": "/tmp/test_video.mp4",
                    "title": "Test Video",
                    "channel": "Test Channel",
                    "resolution": "1080p",
                    "file_size": 10 * 1024 * 1024,
                    "duration": 120,
                    "view_count": 1000,
                    "like_count": 50,
                },
            ):
                with patch(
                    "asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)
                ):
                    await self.downloader.download_and_extract(
                        message, "https://www.youtube.com/watch?v=test_video", "cid"
                    )

        self.db.create_request.assert_called_once()
        self.db.create_video_download.assert_called_once()
        self.db.update_video_download.assert_called_once()
        self.db.update_request_status.assert_called()

    def test_build_metadata_dict(self):
        mock_download = MagicMock()
        mock_download.video_id = "test123"
        mock_download.title = "Test"
        mock_download.channel = "Channel"
        mock_download.channel_id = "UC123"
        mock_download.duration_sec = 120
        mock_download.resolution = "1080p"
        mock_download.file_size_bytes = 1024
        mock_download.upload_date = "20250101"
        mock_download.view_count = 1000
        mock_download.like_count = 100
        mock_download.video_file_path = "/tmp/video.mp4"
        mock_download.subtitle_file_path = "/tmp/video.en.vtt"
        mock_download.thumbnail_file_path = "/tmp/video.jpg"

        metadata = self.downloader._build_metadata_dict(mock_download)

        self.assertEqual(metadata["video_id"], "test123")
        self.assertEqual(metadata["title"], "Test")
        self.assertEqual(metadata["channel"], "Channel")
        self.assertEqual(metadata["resolution"], "1080p")
        self.assertEqual(metadata["file_size"], 1024)


class TestTranscriptFormatting(TestYouTubeDownloader):
    """Test transcript formatting."""

    def test_format_transcript_removes_timestamps(self):
        transcript_data = [
            {"text": "Hello world", "start": 0.0, "duration": 2.0},
            {"text": "This is a test", "start": 2.0, "duration": 2.0},
            {"text": "Final line", "start": 4.0, "duration": 2.0},
        ]

        result = self.downloader._format_transcript(transcript_data)

        self.assertEqual(result, "Hello world This is a test Final line")
        self.assertNotIn("0.0", result)

    def test_format_transcript_removes_duplicate_spaces(self):
        transcript_data = [
            {"text": "Hello  world", "start": 0.0, "duration": 2.0},
            {"text": "  Extra  spaces  ", "start": 2.0, "duration": 2.0},
        ]

        result = self.downloader._format_transcript(transcript_data)

        self.assertEqual(result, "Hello world Extra spaces")
        self.assertNotIn("  ", result)

    def test_format_transcript_empty_entries(self):
        transcript_data = [
            {"text": "Hello", "start": 0.0, "duration": 1.0},
            {"text": "", "start": 1.0, "duration": 1.0},
            {"text": "World", "start": 2.0, "duration": 1.0},
        ]

        result = self.downloader._format_transcript(transcript_data)

        self.assertEqual(result, "Hello World")


class TestNotifications(TestYouTubeDownloader):
    """Test user notification system."""

    @patch(
        "app.adapters.youtube.youtube_downloader.extract_youtube_video_id",
        return_value="test_video",
    )
    @patch("app.adapters.youtube.youtube_downloader.normalize_url")
    @patch("app.adapters.youtube.youtube_downloader.url_hash_sha256")
    async def test_send_download_start_notification(self, mock_hash, mock_normalize, mock_extract):
        mock_normalize.return_value = "https://youtube.com/watch?v=test_video"
        mock_hash.return_value = "hash123"

        message = self._create_mock_message()

        with patch.object(
            self.downloader, "_extract_transcript_api", return_value=("", "en", False)
        ):
            with patch.object(
                self.downloader,
                "_download_video_sync",
                return_value={
                    "video_file_path": "/tmp/video.mp4",
                    "title": "Test",
                    "resolution": "1080p",
                    "file_size": 1024,
                },
            ):
                with patch(
                    "asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)
                ):
                    await self.downloader.download_and_extract(
                        message, "https://www.youtube.com/watch?v=test_video", "cid"
                    )

        self.response_formatter.send_youtube_download_notification.assert_called_once()

    @patch(
        "app.adapters.youtube.youtube_downloader.extract_youtube_video_id",
        return_value="test_video",
    )
    @patch("app.adapters.youtube.youtube_downloader.normalize_url")
    @patch("app.adapters.youtube.youtube_downloader.url_hash_sha256")
    async def test_send_download_complete_notification(
        self, mock_hash, mock_normalize, mock_extract
    ):
        mock_normalize.return_value = "https://youtube.com/watch?v=test_video"
        mock_hash.return_value = "hash123"

        message = self._create_mock_message()

        with patch.object(
            self.downloader, "_extract_transcript_api", return_value=("", "en", False)
        ):
            with patch.object(
                self.downloader,
                "_download_video_sync",
                return_value={
                    "video_file_path": "/tmp/video.mp4",
                    "title": "Test Video",
                    "resolution": "1080p",
                    "file_size": 10 * 1024 * 1024,
                },
            ):
                with patch(
                    "asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)
                ):
                    await self.downloader.download_and_extract(
                        message, "https://www.youtube.com/watch?v=test_video", "cid"
                    )

        self.response_formatter.send_youtube_download_complete_notification.assert_called_once()
        call_args = self.response_formatter.send_youtube_download_complete_notification.call_args
        self.assertEqual(call_args[0][1], "Test Video")

    @patch(
        "app.adapters.youtube.youtube_downloader.extract_youtube_video_id",
        return_value="test_video",
    )
    @patch("app.adapters.youtube.youtube_downloader.normalize_url")
    @patch("app.adapters.youtube.youtube_downloader.url_hash_sha256")
    async def test_silent_mode_no_notifications(self, mock_hash, mock_normalize, mock_extract):
        mock_normalize.return_value = "https://youtube.com/watch?v=test_video"
        mock_hash.return_value = "hash123"

        message = self._create_mock_message()

        with patch.object(
            self.downloader, "_extract_transcript_api", return_value=("", "en", False)
        ):
            with patch.object(
                self.downloader,
                "_download_video_sync",
                return_value={
                    "video_file_path": "/tmp/video.mp4",
                    "title": "Test",
                    "resolution": "1080p",
                    "file_size": 1024,
                },
            ):
                with patch(
                    "asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)
                ):
                    await self.downloader.download_and_extract(
                        message, "https://www.youtube.com/watch?v=test_video", "cid", silent=True
                    )

        # In silent mode, notifications should NOT be called
        self.response_formatter.send_youtube_download_notification.assert_not_called()
        self.response_formatter.send_youtube_download_complete_notification.assert_not_called()


if __name__ == "__main__":
    unittest.main()
