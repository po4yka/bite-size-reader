"""YouTube video downloader using yt-dlp and youtube-transcript-api."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable

from app.adapters.external.formatting.single_url_progress_formatter import (
    SingleURLProgressFormatter,
)
from app.adapters.youtube.youtube_downloader_parts import (
    metadata as _metadata,
    storage as _storage,
    transcript_api as _transcript_api,
    vtt as _vtt,
    yt_dlp_client as _yt_dlp_client,
)
from app.core.async_utils import raise_if_cancelled
from app.core.lang import detect_language
from app.core.url_utils import extract_youtube_video_id, normalize_url, url_hash_sha256
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.video_download_repository import (
    SqliteVideoDownloadRepositoryAdapter,
)
from app.utils.progress_message_updater import ProgressMessageUpdater
from app.utils.typing_indicator import typing_indicator

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.config import AppConfig
    from app.core.progress_tracker import ProgressTracker
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)

# Backwards-compatible aliases (private): keep names stable while moving logic out.
_KNOWN_LANG_CODES = _vtt.KNOWN_LANG_CODES
_VALID_QUALITIES = _yt_dlp_client.VALID_QUALITIES


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

        # Per-URL locks to prevent TOCTOU races on dedupe check
        self._url_locks: dict[str, asyncio.Lock] = {}

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
        progress_tracker: ProgressTracker | None = None,
        *,
        request_id_override: int | None = None,
    ) -> tuple[int, str, str, str, dict]:
        """Download video and extract transcript.

        Returns:
            (req_id, transcript_text, content_source, detected_lang, video_metadata)
        """
        video_id = extract_youtube_video_id(url)
        if not video_id:
            raise ValueError("Invalid YouTube URL: could not extract video ID")

        logger.info(
            "youtube_download_start",
            extra={"video_id": video_id, "url": url, "cid": correlation_id},
        )

        await self._check_storage_limits()
        norm = normalize_url(url)
        dedupe = url_hash_sha256(norm)
        preparation = await self._prepare_download_entry(
            message=message,
            url=url,
            video_id=video_id,
            norm=norm,
            dedupe=dedupe,
            correlation_id=correlation_id,
            request_id_override=request_id_override,
            silent=silent,
        )

        cached_result = preparation["cached_result"]
        req_id = preparation["req_id"]
        if cached_result is not None:
            return cached_result

        if preparation["wait_for_existing_download"]:
            return await self._reuse_in_progress_download_result(
                message=message,
                req_id=req_id,
                correlation_id=correlation_id,
                silent=silent,
            )

        download_id = preparation["download_id"]
        return await self._process_fresh_download(
            message=message,
            url=url,
            video_id=video_id,
            req_id=req_id,
            download_id=download_id,
            correlation_id=correlation_id,
            silent=silent,
            progress_tracker=progress_tracker,
        )

    async def _prepare_download_entry(
        self,
        message: Any,
        url: str,
        video_id: str,
        norm: str,
        dedupe: str,
        correlation_id: str | None,
        request_id_override: int | None,
        silent: bool,
    ) -> dict[str, Any]:
        url_lock = self._url_locks.setdefault(dedupe, asyncio.Lock())
        async with url_lock:
            req_id = await self._resolve_request_id_for_download(
                message=message,
                url=url,
                video_id=video_id,
                norm=norm,
                dedupe=dedupe,
                correlation_id=correlation_id,
                request_id_override=request_id_override,
            )
            existing_download = await self.video_repo.async_get_video_download_by_request(req_id)
            if existing_download and existing_download.get("status") == "completed":
                logger.info(
                    "youtube_video_already_downloaded",
                    extra={"video_id": video_id, "request_id": req_id, "cid": correlation_id},
                )
                result = await self._build_reused_download_result(
                    message=message,
                    req_id=req_id,
                    download=existing_download,
                    correlation_id=correlation_id,
                    silent=silent,
                    reuse_message=(
                        "♻️ Reusing previously downloaded video and transcript. "
                        "Skipping re-download."
                    ),
                    warning_key="youtube_cached_reply_failed",
                    missing_transcript_error=(
                        "❌ Cached video found but no transcript or subtitles were available. "
                        "Try re-downloading with subtitles enabled."
                    ),
                )
                return {
                    "req_id": req_id,
                    "download_id": None,
                    "wait_for_existing_download": False,
                    "cached_result": result,
                }

            if existing_download and existing_download.get("status") in {"pending", "downloading"}:
                logger.info(
                    "youtube_download_in_progress_reuse",
                    extra={
                        "video_id": video_id,
                        "request_id": req_id,
                        "download_id": existing_download.get("id"),
                        "status": existing_download.get("status"),
                        "cid": correlation_id,
                    },
                )
                return {
                    "req_id": req_id,
                    "download_id": existing_download.get("id"),
                    "wait_for_existing_download": True,
                    "cached_result": None,
                }

            download_id = await self.video_repo.async_create_video_download(
                request_id=req_id, video_id=video_id, status="pending"
            )
            return {
                "req_id": req_id,
                "download_id": download_id,
                "wait_for_existing_download": False,
                "cached_result": None,
            }

    async def _resolve_request_id_for_download(
        self,
        message: Any,
        url: str,
        video_id: str,
        norm: str,
        dedupe: str,
        correlation_id: str | None,
        request_id_override: int | None,
    ) -> int:
        if request_id_override is not None:
            return request_id_override

        existing_req = await self.request_repo.async_get_request_by_dedupe_hash(dedupe)
        if isinstance(existing_req, Mapping):
            req_id = int(existing_req["id"])
            logger.info(
                "youtube_dedupe_hit",
                extra={"video_id": video_id, "request_id": req_id, "cid": correlation_id},
            )
            return req_id

        return await self._create_video_request(message, url, norm, dedupe, correlation_id)

    async def _build_reused_download_result(
        self,
        message: Any,
        req_id: int,
        download: dict[str, Any],
        correlation_id: str | None,
        silent: bool,
        reuse_message: str,
        warning_key: str,
        missing_transcript_error: str,
    ) -> tuple[int, str, str, str, dict]:
        if not silent:
            try:
                await self.response_formatter.sender.safe_reply(message, reuse_message)
            except Exception as exc:
                raise_if_cancelled(exc)
                logger.warning(warning_key, exc_info=True)

        metadata = self._build_metadata_dict(download)
        transcript_value = download.get("transcript_text")
        transcript_text = (
            transcript_value if isinstance(transcript_value, str) else str(transcript_value or "")
        )
        if not transcript_text.strip():
            raise ValueError(missing_transcript_error)

        transcript_source = download.get("transcript_source") or "cached"
        detected_lang = download.get("subtitle_language") or detect_language(transcript_text)
        combined_text = self._combine_metadata_and_transcript(metadata, transcript_text)
        return req_id, combined_text, transcript_source, detected_lang, metadata

    async def _reuse_in_progress_download_result(
        self,
        message: Any,
        req_id: int,
        correlation_id: str | None,
        silent: bool,
    ) -> tuple[int, str, str, str, dict]:
        existing_download = await self._await_existing_download_completion(req_id, correlation_id)
        return await self._build_reused_download_result(
            message=message,
            req_id=req_id,
            download=existing_download,
            correlation_id=correlation_id,
            silent=silent,
            reuse_message="⏳ Another request is already processing this video. Reusing the result.",
            warning_key="youtube_in_progress_reply_failed",
            missing_transcript_error=(
                "❌ Reused video download has no transcript/subtitles. Try again later."
            ),
        )

    async def _process_fresh_download(
        self,
        message: Any,
        url: str,
        video_id: str,
        req_id: int,
        download_id: int,
        correlation_id: str | None,
        silent: bool,
        progress_tracker: ProgressTracker | None,
    ) -> tuple[int, str, str, str, dict]:
        output_dir: Path | None = None
        download_succeeded = False
        try:
            await self.video_repo.async_update_video_download_status(
                download_id, "downloading", download_started_at=datetime.now(UTC)
            )
            result, output_dir = await self._run_download_pipeline(
                message=message,
                url=url,
                video_id=video_id,
                req_id=req_id,
                download_id=download_id,
                correlation_id=correlation_id,
                silent=silent,
                progress_tracker=progress_tracker,
            )
            download_succeeded = True
            return result
        except Exception as exc:
            raise_if_cancelled(exc)
            await self.video_repo.async_update_video_download_status(
                download_id, "error", error_text=str(exc)
            )
            await self.request_repo.async_update_request_status(req_id, "error")
            self._audit(
                "ERROR",
                "youtube_download_failed",
                {
                    "video_id": video_id,
                    "request_id": req_id,
                    "error": str(exc),
                    "cid": correlation_id,
                },
            )
            logger.error(
                "youtube_download_failed",
                extra={"video_id": video_id, "error": str(exc), "cid": correlation_id},
            )
            raise
        finally:
            if not download_succeeded and output_dir is not None:
                self._cleanup_partial_download_files(
                    output_dir=output_dir,
                    video_id=video_id,
                    correlation_id=correlation_id,
                )

    async def _run_download_pipeline(
        self,
        message: Any,
        url: str,
        video_id: str,
        req_id: int,
        download_id: int,
        correlation_id: str | None,
        silent: bool,
        progress_tracker: ProgressTracker | None,
    ) -> tuple[tuple[int, str, str, str, dict], Path]:
        async def _draft_stage(text: str, *, force: bool = False) -> None:
            if silent:
                return
            await self.response_formatter.sender.send_message_draft(message, text, force=force)

        use_progress = progress_tracker is not None
        updater: ProgressMessageUpdater | None = None
        typing_ctx: Any | None = None
        start_time = time.time()
        completed_stages: list[tuple[str, float]] = []
        stage_start = time.time()

        if not silent:
            await self.response_formatter.notifications.send_youtube_download_notification(
                message, url, silent=silent
            )
        await _draft_stage("🎥 YouTube: extracting transcript...")

        try:
            updater, typing_ctx = await self._enter_download_feedback(
                progress_tracker=progress_tracker,
                message=message,
                video_id=video_id,
            )
            (
                transcript_text,
                transcript_lang,
                auto_generated,
                transcript_source,
            ) = await self._extract_transcript_api(video_id, correlation_id)
            await _draft_stage("🎥 YouTube: transcript ready, downloading video...")

            stage_start = await self._advance_to_video_download_stage(
                use_progress=use_progress,
                updater=updater,
                video_id=video_id,
                completed_stages=completed_stages,
                stage_start=stage_start,
            )

            output_dir, video_metadata, stage_start = await self._download_video_stage(
                url=url,
                video_id=video_id,
                download_id=download_id,
                message=message,
                silent=silent,
                correlation_id=correlation_id,
                use_progress=use_progress,
                completed_stages=completed_stages,
                stage_start=stage_start,
            )
            (
                transcript_text,
                transcript_lang,
                transcript_source,
            ) = await self._apply_vtt_fallback_if_needed(
                transcript_text=transcript_text,
                transcript_lang=transcript_lang,
                transcript_source=transcript_source,
                video_metadata=video_metadata,
                video_id=video_id,
                correlation_id=correlation_id,
                use_progress=use_progress,
                updater=updater,
                completed_stages=completed_stages,
                stage_start=stage_start,
                draft_stage=_draft_stage,
            )

            if not transcript_text:
                raise ValueError(
                    f"❌ No transcript or subtitles available for this video. "
                    f"Error ID: {correlation_id or 'unknown'}"
                )

            detected_lang = detect_language(transcript_text or "")
            combined_text = self._combine_metadata_and_transcript(video_metadata, transcript_text)
            await self._persist_download_success(
                req_id=req_id,
                download_id=download_id,
                video_metadata=video_metadata,
                transcript_text=transcript_text,
                transcript_lang=transcript_lang,
                auto_generated=auto_generated,
                transcript_source=transcript_source,
                detected_lang=detected_lang,
            )
            await self._finalize_download_success_feedback(
                message=message,
                silent=silent,
                use_progress=use_progress,
                updater=updater,
                video_metadata=video_metadata,
                start_time=start_time,
                draft_stage=_draft_stage,
            )
            if typing_ctx:
                await typing_ctx.__aexit__(None, None, None)

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
            return (
                req_id,
                combined_text,
                transcript_source,
                detected_lang,
                video_metadata,
            ), output_dir
        except Exception as exc:
            await self._finalize_download_error_feedback(
                error=exc,
                correlation_id=correlation_id,
                use_progress=use_progress,
                updater=updater,
                typing_ctx=typing_ctx,
                completed_stages=completed_stages,
                start_time=start_time,
            )
            raise

    async def _enter_download_feedback(
        self,
        progress_tracker: ProgressTracker | None,
        message: Any,
        video_id: str,
    ) -> tuple[ProgressMessageUpdater | None, Any | None]:
        if progress_tracker is not None:
            updater = ProgressMessageUpdater(progress_tracker, message)

            def stage1_formatter(elapsed: float) -> str:
                return SingleURLProgressFormatter.format_youtube_progress(
                    video_id=video_id,
                    stage=1,
                    stage_name="Extracting transcript",
                    stage_elapsed_sec=elapsed,
                    completed_stages=[],
                    total_elapsed_sec=elapsed,
                )

            await updater.start(stage1_formatter)
            return updater, None

        typing_ctx = typing_indicator(self.response_formatter, message, action="upload_video")
        await typing_ctx.__aenter__()
        return None, typing_ctx

    async def _advance_to_video_download_stage(
        self,
        use_progress: bool,
        updater: ProgressMessageUpdater | None,
        video_id: str,
        completed_stages: list[tuple[str, float]],
        stage_start: float,
    ) -> float:
        if not use_progress or updater is None:
            return stage_start

        stage_duration = time.time() - stage_start
        completed_stages.append(("Transcript extracted", stage_duration))
        new_stage_start = time.time()

        def stage2_formatter(elapsed: float) -> str:
            return SingleURLProgressFormatter.format_youtube_progress(
                video_id=video_id,
                stage=2,
                stage_name="Downloading video",
                stage_elapsed_sec=elapsed,
                completed_stages=completed_stages,
                total_elapsed_sec=sum(d for _, d in completed_stages) + elapsed,
            )

        await updater.update_formatter(stage2_formatter)
        return new_stage_start

    async def _download_video_stage(
        self,
        url: str,
        video_id: str,
        download_id: int,
        message: Any,
        silent: bool,
        correlation_id: str | None,
        use_progress: bool,
        completed_stages: list[tuple[str, float]],
        stage_start: float,
    ) -> tuple[Path, dict[str, Any], float]:
        output_dir = self.storage_path / datetime.now().strftime("%Y%m%d")
        output_dir.mkdir(parents=True, exist_ok=True)
        ydl_opts = self._get_ydl_opts(video_id, output_dir)
        async with asyncio.timeout(600.0):
            video_metadata = await asyncio.to_thread(
                self._download_video_sync,
                url,
                ydl_opts,
                download_id,
                message,
                silent,
                correlation_id,
            )

        if not use_progress:
            return output_dir, video_metadata, stage_start

        stage_duration = time.time() - stage_start
        completed_stages.append(("Video downloaded", stage_duration))
        return output_dir, video_metadata, time.time()

    async def _apply_vtt_fallback_if_needed(
        self,
        transcript_text: str,
        transcript_lang: str,
        transcript_source: str,
        video_metadata: dict[str, Any],
        video_id: str,
        correlation_id: str | None,
        use_progress: bool,
        updater: ProgressMessageUpdater | None,
        completed_stages: list[tuple[str, float]],
        stage_start: float,
        draft_stage: Any,
    ) -> tuple[str, str, str]:
        if transcript_text:
            return transcript_text, transcript_lang, transcript_source

        await draft_stage("🎥 YouTube: processing subtitle fallback...")
        if use_progress and updater is not None:

            def stage3_formatter(elapsed: float) -> str:
                return SingleURLProgressFormatter.format_youtube_progress(
                    video_id=video_id,
                    stage=3,
                    stage_name="Processing subtitles",
                    stage_elapsed_sec=elapsed,
                    completed_stages=completed_stages,
                    total_elapsed_sec=sum(d for _, d in completed_stages) + elapsed,
                )

            await updater.update_formatter(stage3_formatter)

        vtt_text, vtt_lang = self._load_transcript_from_vtt(
            video_metadata.get("subtitle_file_path"), correlation_id
        )
        if not vtt_text:
            return transcript_text, transcript_lang, transcript_source

        transcript_text = vtt_text
        transcript_lang = vtt_lang or transcript_lang
        transcript_source = "vtt"
        logger.info(
            "youtube_transcript_vtt_fallback_success",
            extra={"video_id": video_id, "subtitle_lang": transcript_lang, "cid": correlation_id},
        )
        if use_progress:
            stage_duration = time.time() - stage_start
            completed_stages.append(("Subtitles processed", stage_duration))
        return transcript_text, transcript_lang, transcript_source

    async def _persist_download_success(
        self,
        req_id: int,
        download_id: int,
        video_metadata: dict[str, Any],
        transcript_text: str,
        transcript_lang: str,
        auto_generated: bool,
        transcript_source: str,
        detected_lang: str,
    ) -> None:
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
        await self.video_repo.async_update_video_download_status(download_id, "completed")
        await self.request_repo.async_update_request_status(req_id, "ok")
        await self.request_repo.async_update_request_lang_detected(req_id, detected_lang)

    async def _finalize_download_success_feedback(
        self,
        message: Any,
        silent: bool,
        use_progress: bool,
        updater: ProgressMessageUpdater | None,
        video_metadata: dict[str, Any],
        start_time: float,
        draft_stage: Any,
    ) -> None:
        total_elapsed = time.time() - start_time
        await draft_stage("✅ YouTube: transcript and metadata ready. Finalizing summary...")
        if use_progress and updater is not None:
            success_msg = SingleURLProgressFormatter.format_youtube_complete(
                title=video_metadata["title"],
                size_mb=video_metadata["file_size"] / (1024 * 1024),
                total_elapsed_sec=total_elapsed,
                success=True,
            )
            await updater.finalize(success_msg)
            return

        if not silent:
            await self.response_formatter.notifications.send_youtube_download_complete_notification(
                message,
                video_metadata["title"],
                video_metadata["resolution"],
                video_metadata["file_size"] / (1024 * 1024),
                silent=silent,
            )

    async def _finalize_download_error_feedback(
        self,
        error: Exception,
        correlation_id: str | None,
        use_progress: bool,
        updater: ProgressMessageUpdater | None,
        typing_ctx: Any | None,
        completed_stages: list[tuple[str, float]],
        start_time: float,
    ) -> None:
        if use_progress and updater is not None:
            num_completed = len(completed_stages)
            failed_stage = f"Stage {num_completed + 1}/3" if num_completed < 3 else "Processing"
            error_msg = SingleURLProgressFormatter.format_youtube_complete(
                title="",
                size_mb=0,
                total_elapsed_sec=time.time() - start_time,
                success=False,
                error_msg=str(error),
                correlation_id=correlation_id,
                failed_stage=failed_stage,
            )
            await updater.finalize(error_msg)
            return

        if typing_ctx:
            await typing_ctx.__aexit__(None, None, None)

    def _cleanup_partial_download_files(
        self,
        output_dir: Path,
        video_id: str,
        correlation_id: str | None,
    ) -> None:
        try:
            if output_dir.exists():
                deleted_count = _storage.cleanup_partial_download_files(
                    output_dir=output_dir,
                    video_id=video_id,
                )
                if deleted_count > 0:
                    logger.info(
                        "youtube_partial_download_cleaned",
                        extra={
                            "video_id": video_id,
                            "cid": correlation_id,
                            "files_removed": deleted_count,
                        },
                    )
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.warning("youtube_partial_cleanup_failed", exc_info=True)

    async def _await_existing_download_completion(
        self,
        req_id: int,
        correlation_id: str | None,
        *,
        timeout_sec: float = 620.0,
        poll_interval_sec: float = 1.0,
    ) -> dict[str, Any]:
        """Wait for an in-flight download to complete and return the final row."""
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            existing_download = await self.video_repo.async_get_video_download_by_request(req_id)
            if not isinstance(existing_download, dict):
                await asyncio.sleep(poll_interval_sec)
                continue

            status = str(existing_download.get("status") or "").lower()
            if status == "completed":
                return existing_download
            if status == "error":
                error_text = existing_download.get("error_text") or "YouTube download failed"
                raise ValueError(f"❌ {error_text}")

            await asyncio.sleep(poll_interval_sec)

        raise TimeoutError(
            "Timed out waiting for an existing YouTube download to finish. Please try again."
        )

    async def _extract_transcript_api(
        self, video_id: str, correlation_id: str | None
    ) -> tuple[str, str, bool, str]:
        return await _transcript_api.extract_transcript_via_api(
            video_id=video_id,
            preferred_langs=self.cfg.youtube.subtitle_languages,
            correlation_id=correlation_id,
            youtube_transcript_api=YouTubeTranscriptApi,
            no_transcript_found_exc=NoTranscriptFound,
            transcripts_disabled_exc=TranscriptsDisabled,
            video_unavailable_exc=VideoUnavailable,
            raise_if_cancelled=raise_if_cancelled,
            max_transcript_chars=self._MAX_TRANSCRIPT_CHARS,
            log=logger,
        )

    _MAX_TRANSCRIPT_CHARS = 500_000  # ~125k tokens, sufficient for most LLMs

    def _format_transcript(self, transcript_data: list[dict]) -> str:
        return _transcript_api.format_transcript(
            transcript_data,
            max_chars=self._MAX_TRANSCRIPT_CHARS,
            log=logger,
        )

    def _get_ydl_opts(self, video_id: str, output_path: Path) -> dict:
        return cast(
            "dict",
            _yt_dlp_client.build_ydl_opts(
                video_id=video_id,
                output_path=output_path,
                preferred_quality=self.cfg.youtube.preferred_quality,
                subtitle_languages=self.cfg.youtube.subtitle_languages,
                max_video_size_mb=self.cfg.youtube.max_video_size_mb,
            ),
        )

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
        _ = download_id
        _ = message
        _ = silent
        return cast(
            "dict",
            _yt_dlp_client.download_video_sync(
                url=url,
                ydl_opts=cast("dict[str, Any]", ydl_opts),
                subtitle_languages=self.cfg.youtube.subtitle_languages,
                correlation_id=correlation_id,
                extract_youtube_video_id=extract_youtube_video_id,
                yt_dlp_module=yt_dlp,
            ),
        )

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
        """Calculate total storage used by video-related files in bytes."""
        return _storage.calculate_storage_usage(self.storage_path)

    def _auto_cleanup_storage(self, current_usage: int, max_storage: int) -> int:
        """Remove old files until under budget or no candidates remain.

        Returns reclaimed bytes.
        """
        return _storage.auto_cleanup_storage(
            self.storage_path,
            current_usage=current_usage,
            max_storage=max_storage,
            retention_days=self.cfg.youtube.cleanup_after_days,
            now=datetime.now(UTC),
        )

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
        return _vtt.parse_vtt_file(path, known_lang_codes=_KNOWN_LANG_CODES)

    def _format_metadata_header(self, metadata: dict) -> str:
        """Create a concise metadata header to give the summarizer context."""
        return _metadata.format_metadata_header(metadata)

    def _format_duration(self, duration: int | None) -> str:
        return _metadata.format_duration(duration)

    def _combine_metadata_and_transcript(self, metadata: dict, transcript_text: str) -> str:
        """Prepend metadata header to transcript for better summarization context."""
        return _metadata.combine_metadata_and_transcript(metadata, transcript_text)

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
