"""YouTube video downloader using yt-dlp and youtube-transcript-api."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable

from app.core.async_utils import raise_if_cancelled
from app.core.lang import detect_language
from app.core.url_utils import extract_youtube_video_id, normalize_url, url_hash_sha256
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.video_download_repository import (
    SqliteVideoDownloadRepositoryAdapter,
)

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


class YouTubeDownloader:
    """Handles YouTube video downloading with yt-dlp and transcript extraction."""

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.response_formatter = response_formatter
        self._audit = audit_func
        self.video_repo = SqliteVideoDownloadRepositoryAdapter(db)
        self.request_repo = SqliteRequestRepositoryAdapter(db)

        # Create storage directory
        self.storage_path = Path(cfg.youtube.storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Progress tracking
        self._download_progress: dict[str, dict] = {}
        self._progress_message_ids: dict[str, int] = {}

    async def download_and_extract(
        self,
        message: Any,
        url: str,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
        silent: bool = False,
    ) -> tuple[int, str, str, str, dict]:
        """Download video and extract transcript.

        Returns:
            (req_id, transcript_text, content_source, detected_lang, video_metadata)
        """
        # Extract video ID
        video_id = extract_youtube_video_id(url)
        if not video_id:
            raise ValueError("Invalid YouTube URL: could not extract video ID")

        logger.info(
            "youtube_download_start",
            extra={"video_id": video_id, "url": url, "cid": correlation_id},
        )

        # Check storage limits (may trigger cleanup)
        await self._check_storage_limits()

        # Normalize URL for deduplication
        norm = normalize_url(url)
        dedupe = url_hash_sha256(norm)

        # Fetch existing request by dedupe hash
        existing_req = await self.request_repo.async_get_request_by_dedupe_hash(dedupe)
        if isinstance(existing_req, Mapping):
            req_id = int(existing_req["id"])
            logger.info(
                "youtube_dedupe_hit",
                extra={"video_id": video_id, "request_id": req_id, "cid": correlation_id},
            )
        else:
            # Create new request
            req_id = await self._create_video_request(message, url, norm, dedupe, correlation_id)

        # Check for existing download
        existing_download = await self.video_repo.async_get_video_download_by_request(req_id)
        if existing_download and existing_download.get("status") == "completed":
            logger.info(
                "youtube_video_already_downloaded",
                extra={"video_id": video_id, "request_id": req_id, "cid": correlation_id},
            )
            metadata = self._build_metadata_dict(existing_download)
            transcript_text = existing_download.get("transcript_text") or ""
            transcript_source = existing_download.get("transcript_source") or "cached"
            detected_lang = existing_download.get("subtitle_language") or detect_language(
                transcript_text
            )
            combined_text = self._combine_metadata_and_transcript(metadata, transcript_text)

            if not combined_text.strip():
                raise ValueError(
                    "❌ Cached video found but no transcript or subtitles were available. "
                    "Try re-downloading with subtitles enabled."
                )

            if not silent:
                try:
                    await self.response_formatter.safe_reply(
                        message,
                        "♻️ Reusing previously downloaded video and transcript. Skipping re-download.",
                    )
                except Exception:
                    logger.debug("youtube_cached_reply_failed", exc_info=True)

            return (
                req_id,
                combined_text,
                transcript_source,
                detected_lang,
                metadata,
            )

        # 1. Create initial download record
        download_id = await self.video_repo.async_create_video_download(
            request_id=req_id, video_id=video_id, status="pending"
        )

        try:
            # 2. Update status to downloading
            await self.video_repo.async_update_video_download_status(
                download_id, "downloading", download_started_at=datetime.now(UTC)
            )

            # Notify user: starting download
            if not silent:
                await self.response_formatter.send_youtube_download_notification(
                    message, url, silent=silent
                )

            # Step 1: Extract transcript using youtube-transcript-api (with retries)
            (
                transcript_text,
                transcript_lang,
                auto_generated,
                transcript_source,
            ) = await self._extract_transcript_api(video_id, correlation_id)

            # Step 2: Download video with yt-dlp
            output_dir = self.storage_path / datetime.now().strftime("%Y%m%d")
            output_dir.mkdir(parents=True, exist_ok=True)

            ydl_opts = self._get_ydl_opts(video_id, output_dir)

            # Download in thread pool (yt-dlp is sync)
            video_metadata = await asyncio.to_thread(
                self._download_video_sync,
                url,
                ydl_opts,
                download_id,
                message,
                silent,
                correlation_id,
            )

            # Fallback to downloaded VTT subtitles if API transcript is missing
            if not transcript_text:
                vtt_text, vtt_lang = self._load_transcript_from_vtt(
                    video_metadata.get("subtitle_file_path"), correlation_id
                )
                if vtt_text:
                    transcript_text = vtt_text
                    transcript_lang = vtt_lang or transcript_lang
                    transcript_source = "vtt"
                    _ = auto_generated  # Mark as used/shadowed if we switch to VTT
                    logger.info(
                        "youtube_transcript_vtt_fallback_success",
                        extra={
                            "video_id": video_id,
                            "subtitle_lang": transcript_lang,
                            "cid": correlation_id,
                        },
                    )

            if not transcript_text:
                raise ValueError(
                    f"❌ No transcript or subtitles available for this video. "
                    f"Error ID: {correlation_id or 'unknown'}"
                )

            # Detect language from transcript
            detected_lang = detect_language(transcript_text or "")
            combined_text = self._combine_metadata_and_transcript(video_metadata, transcript_text)

            # Update database with complete metadata + transcript
            await self.video_repo.async_update_video_download(
                download_id,
                title=video_metadata.get("title"),
                channel=video_metadata.get("channel"),
                channel_id=video_metadata.get("channel_id"),
                duration_sec=video_metadata.get("duration"),
                upload_date=video_metadata.get("upload_date"),
                view_count=video_metadata.get("view_count"),
                like_count=video_metadata.get("like_count"),
                resolution=video_metadata.get("resolution"),
                file_size_bytes=video_metadata.get("file_size"),
                video_codec=video_metadata.get("vcodec"),
                audio_codec=video_metadata.get("acodec"),
                format_id=video_metadata.get("format_id"),
                transcript_text=transcript_text,
                subtitle_language=transcript_lang,
                auto_generated=auto_generated,
                transcript_source=transcript_source,
            )

            # Mark download as completed so cached lookups work
            await self.video_repo.async_update_video_download_status(download_id, "completed")

            # Update request status
            await self.request_repo.async_update_request_status(req_id, "ok")
            await self.request_repo.async_update_request_lang_detected(req_id, detected_lang)

            # Notify user: download complete
            if not silent:
                await self.response_formatter.send_youtube_download_complete_notification(
                    message,
                    video_metadata["title"],
                    video_metadata["resolution"],
                    video_metadata["file_size"] / (1024 * 1024),  # MB
                    silent=silent,
                )

            self._audit(
                "INFO",
                "youtube_download_complete",
                {
                    "video_id": video_id,
                    "request_id": req_id,
                    "download_id": download_id,
                    "file_size_mb": video_metadata["file_size"] / (1024 * 1024),
                    "cid": correlation_id,
                },
            )

            return req_id, combined_text, transcript_source, detected_lang, video_metadata

        except Exception as e:
            raise_if_cancelled(e)
            if download_id:
                await self.video_repo.async_update_video_download_status(
                    download_id, "error", error_text=str(e)
                )
            await self.request_repo.async_update_request_status(req_id, "error")

            self._audit(
                "ERROR",
                "youtube_download_failed",
                {
                    "video_id": video_id,
                    "request_id": req_id,
                    "error": str(e),
                    "cid": correlation_id,
                },
            )

            logger.error(
                "youtube_download_failed",
                extra={"video_id": video_id, "error": str(e), "cid": correlation_id},
            )
            raise

    async def _extract_transcript_api(
        self, video_id: str, correlation_id: str | None
    ) -> tuple[str, str, bool, str]:
        """Extract transcript using youtube-transcript-api with a light retry.

        Returns:
            (transcript_text, language, auto_generated, transcript_source)
        """
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                # Preferred languages from config
                preferred_langs = self.cfg.youtube.subtitle_languages

                # Try to get transcript in preferred language
                transcript_list = await asyncio.to_thread(
                    cast("Any", YouTubeTranscriptApi).list_transcripts,
                    video_id,
                )

                transcript = None
                auto_generated = False
                selected_lang = "en"

                # Try manually created transcripts first
                try:
                    for lang in preferred_langs:
                        try:
                            transcript = transcript_list.find_transcript([lang])
                            selected_lang = lang
                            auto_generated = False
                            logger.info(
                                "youtube_transcript_manual_found",
                                extra={
                                    "video_id": video_id,
                                    "language": lang,
                                    "cid": correlation_id,
                                },
                            )
                            break
                        except NoTranscriptFound:
                            continue
                except (TranscriptsDisabled, VideoUnavailable):
                    # Re-raise these to be handled by outer try-except
                    raise
                except Exception as e:
                    # Log unexpected errors but continue to auto-generated fallback
                    logger.warning(
                        "youtube_transcript_manual_search_error",
                        extra={
                            "video_id": video_id,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "cid": correlation_id,
                        },
                    )

                # Fallback to auto-generated if no manual transcript found
                if not transcript:
                    try:
                        transcript = transcript_list.find_generated_transcript(preferred_langs)
                        selected_lang = transcript.language_code
                        auto_generated = True
                        logger.info(
                            "youtube_transcript_auto_found",
                            extra={
                                "video_id": video_id,
                                "language": selected_lang,
                                "cid": correlation_id,
                            },
                        )
                    except NoTranscriptFound:
                        logger.warning(
                            "youtube_transcript_not_found",
                            extra={"video_id": video_id, "cid": correlation_id},
                        )
                        return "", "en", False, "youtube-transcript-api"

                # Fetch transcript data
                transcript_data = await asyncio.to_thread(transcript.fetch)

                # Format transcript text
                transcript_text = self._format_transcript(transcript_data)

                logger.info(
                    "youtube_transcript_extracted",
                    extra={
                        "video_id": video_id,
                        "language": selected_lang,
                        "auto_generated": auto_generated,
                        "length": len(transcript_text),
                        "cid": correlation_id,
                    },
                )

                return transcript_text, selected_lang, auto_generated, "youtube-transcript-api"

            except TranscriptsDisabled as e:
                logger.warning(
                    "youtube_transcript_disabled",
                    extra={"video_id": video_id, "error": str(e), "cid": correlation_id},
                )
                logger.info(
                    "youtube_continuing_without_transcript",
                    extra={"video_id": video_id, "cid": correlation_id},
                )
                return "", "en", False, "youtube-transcript-api"
            except VideoUnavailable as e:
                logger.error(
                    "youtube_transcript_video_unavailable",
                    extra={"video_id": video_id, "error": str(e), "cid": correlation_id},
                )
                raise ValueError(
                    "❌ Video is unavailable or does not exist. The video may have been deleted or made private."
                ) from e
            except Exception as e:
                raise_if_cancelled(e)
                last_error = e
                logger.warning(
                    "youtube_transcript_extraction_failed",
                    extra={
                        "video_id": video_id,
                        "error": str(e),
                        "attempt": attempt + 1,
                        "cid": correlation_id,
                    },
                )
                if attempt == 0:
                    await asyncio.sleep(1)
                    continue
                return "", "en", False, "youtube-transcript-api"

        # Should not reach here, but return safe empty result
        logger.warning(
            "youtube_transcript_extraction_exhausted",
            extra={"video_id": video_id, "error": str(last_error), "cid": correlation_id},
        )
        return "", "en", False, "youtube-transcript-api"

    def _format_transcript(self, transcript_data: list[dict]) -> str:
        """Format transcript data into readable text with timestamps.

        Args:
            transcript_data: List of transcript entries with 'text', 'start', 'duration'

        Returns:
            Formatted transcript text
        """
        lines = []
        for entry in transcript_data:
            text = entry.get("text", "").strip()
            if text:
                # Don't include timestamps in the final transcript for better LLM processing
                # Just join all text naturally
                lines.append(text)

        # Join with spaces and clean up, removing duplicate spaces
        transcript = " ".join(lines)
        # Remove duplicate spaces
        return " ".join(transcript.split())

    def _get_ydl_opts(self, video_id: str, output_path: Path) -> dict:
        """Get yt-dlp options for 1080p download with subtitles."""
        quality = self.cfg.youtube.preferred_quality.rstrip("p")  # Remove 'p' suffix

        return {
            # Video format: best video up to configured quality + best audio, merge to mp4
            "format": f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}]",
            # Output template: organized by date and video ID
            "outtmpl": str(output_path / f"{video_id}_%(title)s.%(ext)s"),
            # Download subtitles/captions
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": self.cfg.youtube.subtitle_languages,
            "subtitlesformat": "vtt",
            # Write video metadata to JSON file
            "writeinfojson": True,
            # Write thumbnail
            "writethumbnail": True,
            # Prefer FFmpeg for merging (better quality)
            "prefer_ffmpeg": True,
            "merge_output_format": "mp4",
            # Quiet mode (we handle logging)
            "quiet": True,
            "no_warnings": False,
            # Abort on error
            "ignoreerrors": False,
            # Max file size check
            "max_filesize": self.cfg.youtube.max_video_size_mb * 1024 * 1024,
        }

    def _download_video_sync(
        self,
        url: str,
        ydl_opts: dict,
        download_id: int,
        message: Any,
        silent: bool,
        correlation_id: str | None,
    ) -> dict:
        """Synchronous download using yt-dlp.

        This runs in a thread pool to avoid blocking the async event loop.
        """
        video_id = extract_youtube_video_id(url)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract info without downloading first (to check size and get metadata)
            try:
                info = ydl.extract_info(url, download=False)
            except yt_dlp.utils.DownloadError as e:
                error_msg = str(e).lower()
                logger.error(
                    "yt_dlp_extract_info_failed",
                    extra={"url": url, "error": str(e), "cid": correlation_id},
                )

                # Categorize common errors with user-friendly messages
                if "sign in to confirm your age" in error_msg or "age-restricted" in error_msg:
                    raise ValueError(
                        "❌ This video is age-restricted and cannot be downloaded. "
                        "YouTube requires login/age verification for this content."
                    ) from e
                if "video is not available" in error_msg or "video unavailable" in error_msg:
                    raise ValueError(
                        "❌ Video is not available. It may be private, deleted, or geo-blocked in your region."
                    ) from e
                if "private video" in error_msg:
                    raise ValueError("❌ This video is private and cannot be accessed.") from e
                if "members-only" in error_msg or "join this channel" in error_msg:
                    raise ValueError(
                        "❌ This video is members-only content. YouTube Premium or channel membership required."
                    ) from e
                if "this live event will begin" in error_msg or "premieres in" in error_msg:
                    raise ValueError(
                        "❌ This video is a scheduled premiere or upcoming live stream. "
                        "Please try again after it starts."
                    ) from e
                if "copyright" in error_msg:
                    raise ValueError("❌ Video unavailable due to copyright restrictions.") from e
                if "geo" in error_msg or "not available in your country" in error_msg:
                    raise ValueError(
                        "❌ This video is geo-blocked and not available in your region."
                    ) from e
                # Generic extraction error
                raise ValueError(f"❌ Failed to extract video information: {str(e)[:200]}") from e
            except Exception as e:
                logger.error(
                    "yt_dlp_extract_info_failed",
                    extra={"url": url, "error": str(e), "cid": correlation_id},
                )
                raise ValueError(
                    f"❌ Unexpected error extracting video info: {str(e)[:200]}"
                ) from e

            # Check file size
            filesize = info.get("filesize") or info.get("filesize_approx", 0)
            max_size = self.cfg.youtube.max_video_size_mb * 1024 * 1024

            if filesize > max_size:
                raise ValueError(
                    f"❌ Video too large: {filesize / 1024 / 1024:.1f}MB exceeds maximum allowed size "
                    f"({self.cfg.youtube.max_video_size_mb}MB). Try a lower quality setting."
                )

            # Download video
            try:
                ydl.download([url])
            except yt_dlp.utils.DownloadError as e:
                error_msg = str(e).lower()
                logger.error(
                    "yt_dlp_download_failed",
                    extra={"url": url, "error": str(e), "cid": correlation_id},
                )

                # Check for specific download errors
                if "http error 429" in error_msg or "too many requests" in error_msg:
                    raise ValueError(
                        "❌ YouTube rate limit exceeded. Please try again in a few minutes."
                    ) from e
                if "http error 403" in error_msg:
                    raise ValueError(
                        "❌ Access forbidden. Video may require authentication or is geo-blocked."
                    ) from e
                if "http error 404" in error_msg:
                    raise ValueError(
                        "❌ Video not found. It may have been deleted or the URL is incorrect."
                    ) from e
                if "timed out" in error_msg or "timeout" in error_msg:
                    raise ValueError(
                        "❌ Download timed out. Please try again or check your internet connection."
                    ) from e
                if "connection" in error_msg:
                    raise ValueError(
                        "❌ Network connection error. Please check your internet connection and try again."
                    ) from e
                raise ValueError(f"❌ Download failed: {str(e)[:200]}") from e
            except Exception as e:
                logger.error(
                    "yt_dlp_download_failed",
                    extra={"url": url, "error": str(e), "cid": correlation_id},
                )
                raise ValueError(f"❌ Unexpected download error: {str(e)[:200]}") from e

            # Get downloaded file paths
            video_file = ydl.prepare_filename(info)
            video_path = Path(video_file)

            # Find subtitle file (may have different language codes)
            subtitle_file = None
            for lang in self.cfg.youtube.subtitle_languages:
                sub_path = video_path.with_suffix(f".{lang}.vtt")
                if sub_path.exists():
                    subtitle_file = str(sub_path)
                    break

            metadata_file = video_path.with_suffix(".info.json")
            thumbnail_file = None
            # Thumbnail can have various extensions
            for ext in [".jpg", ".png", ".webp"]:
                thumb_path = video_path.with_suffix(ext)
                if thumb_path.exists():
                    thumbnail_file = str(thumb_path)
                    break

            # Load metadata if available
            if metadata_file.exists():
                with open(metadata_file, encoding="utf-8") as f:
                    metadata = json.load(f)
            else:
                metadata = info

            return {
                "video_file_path": str(video_file),
                "subtitle_file_path": subtitle_file,
                "metadata_file_path": str(metadata_file) if metadata_file.exists() else None,
                "thumbnail_file_path": thumbnail_file,
                "video_id": metadata.get("id", video_id),
                "title": metadata.get("title", "Unknown"),
                "channel": metadata.get("uploader") or metadata.get("channel", "Unknown"),
                "channel_id": metadata.get("channel_id"),
                "duration": metadata.get("duration"),
                "resolution": f"{metadata.get('height', '?')}p",
                "file_size": video_path.stat().st_size if video_path.exists() else 0,
                "upload_date": metadata.get("upload_date"),
                "view_count": metadata.get("view_count"),
                "like_count": metadata.get("like_count"),
                "vcodec": metadata.get("vcodec"),
                "acodec": metadata.get("acodec"),
                "format_id": metadata.get("format_id"),
            }

    async def _create_video_request(
        self, message: Any, url: str, norm: str, dedupe: str, correlation_id: str | None
    ) -> int:
        """Create a new request in the database for YouTube video."""
        chat_obj = getattr(message, "chat", None)
        chat_id_raw = getattr(chat_obj, "id", 0) if chat_obj is not None else None
        chat_id = int(chat_id_raw) if chat_id_raw is not None else None

        from_user_obj = getattr(message, "from_user", None)
        user_id_raw = getattr(from_user_obj, "id", 0) if from_user_obj is not None else None
        user_id = int(user_id_raw) if user_id_raw is not None else None

        msg_id_raw = getattr(message, "id", getattr(message, "message_id", 0))
        input_message_id = int(msg_id_raw) if msg_id_raw is not None else None

        req_id = await self.request_repo.async_create_request(
            type_="url",
            status="pending",
            correlation_id=correlation_id,
            chat_id=chat_id,
            user_id=user_id,
            input_url=url,
            normalized_url=norm,
            dedupe_hash=dedupe,
            input_message_id=input_message_id,
            content_text=url,  # Store the URL as content text for consistency
            route_version=1,
        )

        logger.info(
            "youtube_request_created",
            extra={"request_id": req_id, "url": url, "cid": correlation_id},
        )

        return req_id

    async def _check_storage_limits(self) -> None:
        """Check if storage limits would be exceeded and trigger cleanup if needed."""
        current_usage = self._calculate_storage_usage()
        max_storage = self.cfg.youtube.max_storage_gb * 1024 * 1024 * 1024
        threshold = max_storage * 0.9

        if current_usage > threshold and self.cfg.youtube.auto_cleanup_enabled:
            reclaimed = await asyncio.to_thread(
                self._auto_cleanup_storage, current_usage, max_storage
            )
            current_usage = self._calculate_storage_usage()
            logger.info(
                "youtube_storage_cleanup_attempted",
                extra={
                    "current_gb": current_usage / 1024 / 1024 / 1024,
                    "max_gb": self.cfg.youtube.max_storage_gb,
                    "reclaimed_gb": reclaimed / 1024 / 1024 / 1024,
                },
            )

        if current_usage > max_storage:
            raise ValueError(
                "❌ Storage limit exceeded. Unable to download new videos until cleanup frees space."
            )

    def _calculate_storage_usage(self) -> int:
        """Calculate total storage used by videos in bytes."""
        total = 0
        try:
            for file_path in self.storage_path.rglob("*.mp4"):
                if file_path.is_file():
                    total += file_path.stat().st_size
        except Exception as e:
            logger.warning("youtube_storage_calculation_failed", extra={"error": str(e)})

        return total

    def _auto_cleanup_storage(self, current_usage: int, max_storage: int) -> int:
        """Remove old files until under budget or no candidates remain.

        Returns reclaimed bytes.
        """
        reclaimed = 0
        retention_days = self.cfg.youtube.cleanup_after_days
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        eligible_suffixes = {".mp4", ".info.json", ".vtt", ".jpg", ".png", ".webp"}

        candidates: list[tuple[Path, int, float]] = []
        for file_path in self.storage_path.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in eligible_suffixes:
                continue
            try:
                stat = file_path.stat()
            except OSError:
                continue
            modified = datetime.fromtimestamp(stat.st_mtime, UTC)
            if modified < cutoff:
                candidates.append((file_path, stat.st_size, stat.st_mtime))

        candidates.sort(key=lambda x: x[2])  # oldest first

        for path, size, _ in candidates:
            if current_usage - reclaimed <= max_storage * 0.9:
                break
            try:
                path.unlink()
                reclaimed += size
            except OSError as exc:
                logger.warning(
                    "youtube_cleanup_delete_failed",
                    extra={"path": str(path), "error": str(exc)},
                )
                continue

        logger.info(
            "youtube_cleanup_completed",
            extra={
                "candidates": len(candidates),
                "reclaimed_bytes": reclaimed,
                "retention_days": retention_days,
            },
        )
        return reclaimed

    def _load_transcript_from_vtt(
        self, subtitle_path: str | None, correlation_id: str | None
    ) -> tuple[str, str | None]:
        """Load transcript text from a downloaded VTT subtitle file."""
        if not subtitle_path:
            return "", None

        try:
            text, lang = self._parse_vtt_file(Path(subtitle_path))
            if text:
                logger.info(
                    "youtube_transcript_vtt_loaded",
                    extra={"subtitle_lang": lang, "cid": correlation_id},
                )
            return text, lang
        except FileNotFoundError:
            logger.warning(
                "youtube_transcript_vtt_missing",
                extra={"subtitle_path": subtitle_path, "cid": correlation_id},
            )
            return "", None
        except Exception as exc:
            logger.warning(
                "youtube_transcript_vtt_parse_failed",
                extra={"subtitle_path": subtitle_path, "error": str(exc), "cid": correlation_id},
            )
            return "", None

    def _parse_vtt_file(self, path: Path) -> tuple[str, str | None]:
        """Parse a VTT subtitle file into plain text."""
        lines: list[str] = []
        lang = None

        # Try to infer language code from filename suffix, e.g., .en.vtt
        parts = path.name.split(".")
        if len(parts) >= 3:
            lang = parts[-2]

        with path.open(encoding="utf-8") as f:
            for raw in f:
                stripped = raw.strip()
                if not stripped:
                    continue
                if stripped.startswith("WEBVTT"):
                    continue
                if "-->" in stripped:
                    continue
                if stripped.isdigit():
                    continue
                lines.append(stripped)

        text = " ".join(lines)
        return " ".join(text.split()), lang

    def _format_metadata_header(self, metadata: dict) -> str:
        """Create a concise metadata header to give the summarizer context."""
        title = metadata.get("title")
        channel = metadata.get("channel")
        duration = metadata.get("duration")
        resolution = metadata.get("resolution")

        parts = []
        if title:
            parts.append(f"Title: {title}")
        if channel:
            parts.append(f"Channel: {channel}")
        if duration:
            parts.append(self._format_duration(duration))
        if resolution:
            parts.append(f"Resolution: {resolution}")

        return " | ".join(parts)

    def _format_duration(self, duration: int | None) -> str:
        if duration is None:
            return ""
        minutes, seconds = divmod(int(duration), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"Duration: {hours}h {minutes}m {seconds}s"
        if minutes:
            return f"Duration: {minutes}m {seconds}s"
        return f"Duration: {seconds}s"

    def _combine_metadata_and_transcript(self, metadata: dict, transcript_text: str) -> str:
        """Prepend metadata header to transcript for better summarization context."""
        header = self._format_metadata_header(metadata)
        preamble = (
            "[Source: YouTube video transcript. "
            "Summarize this as video content — "
            "use watch time instead of reading time, "
            "and set source_type to an appropriate value for video content.]"
        )
        parts: list[str] = [preamble]
        if header:
            parts.append(header)
        if transcript_text:
            parts.append(transcript_text)
        return "\n\n".join(parts)

    def _build_metadata_dict(self, download: dict | Any) -> dict:
        """Build metadata dictionary from VideoDownload model or dict."""
        if isinstance(download, dict):
            return {
                "video_id": download.get("video_id"),
                "title": download.get("title"),
                "channel": download.get("channel"),
                "channel_id": download.get("channel_id"),
                "duration": download.get("duration_sec"),
                "resolution": download.get("resolution"),
                "file_size": download.get("file_size_bytes"),
                "upload_date": download.get("upload_date"),
                "view_count": download.get("view_count"),
                "like_count": download.get("like_count"),
                "video_file_path": download.get("video_file_path"),
                "subtitle_file_path": download.get("subtitle_file_path"),
                "thumbnail_file_path": download.get("thumbnail_file_path"),
            }

        return {
            "video_id": download.video_id,
            "title": download.title,
            "channel": download.channel,
            "channel_id": download.channel_id,
            "duration": download.duration_sec,
            "resolution": download.resolution,
            "file_size": download.file_size_bytes,
            "upload_date": download.upload_date,
            "view_count": download.view_count,
            "like_count": download.like_count,
            "video_file_path": download.video_file_path,
            "subtitle_file_path": download.subtitle_file_path,
            "thumbnail_file_path": download.thumbnail_file_path,
        }
