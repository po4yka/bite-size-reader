"""Feedback and progress orchestration for YouTube extraction."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.adapters.external.formatting.single_url_progress_formatter import (
    SingleURLProgressFormatter,
)
from app.core.logging_utils import get_logger
from app.utils.progress_message_updater import ProgressMessageUpdater
from app.utils.typing_indicator import typing_indicator

if TYPE_CHECKING:
    from app.adapters.content.platform_extraction.models import PlatformExtractionRequest
    from app.adapters.external.response_formatter import ResponseFormatter

logger = get_logger(__name__)


@dataclass(slots=True)
class YouTubeFeedbackState:
    updater: ProgressMessageUpdater | None = None
    typing_ctx: Any | None = None
    start_time: float = field(default_factory=time.time)
    stage_start: float = field(default_factory=time.time)
    completed_stages: list[tuple[str, float]] = field(default_factory=list)


class YouTubeFeedbackService:
    """Own progress tracker, typing indicator, and notification flow."""

    def __init__(self, *, response_formatter: ResponseFormatter) -> None:
        self._response_formatter = response_formatter

    async def start(
        self,
        *,
        request: PlatformExtractionRequest,
        video_id: str,
    ) -> YouTubeFeedbackState:
        state = YouTubeFeedbackState()
        if request.mode != "interactive" or request.message is None:
            return state

        if not request.silent:
            await self._response_formatter.send_youtube_download_notification(
                request.message,
                request.url_text,
                silent=request.silent,
            )
        await self._draft_stage(request=request, text="🎥 YouTube: extracting transcript...")

        if request.progress_tracker is not None:
            updater = ProgressMessageUpdater(request.progress_tracker, request.message)

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
            state.updater = updater
            return state

        state.typing_ctx = typing_indicator(
            self._response_formatter,
            request.message,
            action="upload_video",
        )
        await state.typing_ctx.__aenter__()
        return state

    async def mark_transcript_ready(
        self,
        *,
        state: YouTubeFeedbackState,
        request: PlatformExtractionRequest,
        video_id: str,
    ) -> None:
        await self._draft_stage(
            request=request,
            text="🎥 YouTube: transcript ready, downloading video...",
        )
        if state.updater is None:
            return

        stage_duration = time.time() - state.stage_start
        state.completed_stages.append(("Transcript extracted", stage_duration))
        state.stage_start = time.time()

        def stage2_formatter(elapsed: float) -> str:
            return SingleURLProgressFormatter.format_youtube_progress(
                video_id=video_id,
                stage=2,
                stage_name="Downloading video",
                stage_elapsed_sec=elapsed,
                completed_stages=state.completed_stages,
                total_elapsed_sec=sum(d for _, d in state.completed_stages) + elapsed,
            )

        await state.updater.update_formatter(stage2_formatter)

    async def mark_subtitle_fallback(
        self,
        *,
        state: YouTubeFeedbackState,
        request: PlatformExtractionRequest,
        video_id: str,
    ) -> None:
        await self._draft_stage(
            request=request,
            text="🎥 YouTube: processing subtitle fallback...",
        )
        if state.updater is None:
            return

        def stage3_formatter(elapsed: float) -> str:
            return SingleURLProgressFormatter.format_youtube_progress(
                video_id=video_id,
                stage=3,
                stage_name="Processing subtitles",
                stage_elapsed_sec=elapsed,
                completed_stages=state.completed_stages,
                total_elapsed_sec=sum(d for _, d in state.completed_stages) + elapsed,
            )

        await state.updater.update_formatter(stage3_formatter)

    async def finalize_success(
        self,
        *,
        state: YouTubeFeedbackState,
        request: PlatformExtractionRequest,
        video_metadata: dict[str, Any],
    ) -> None:
        await self._draft_stage(
            request=request,
            text="✅ YouTube: transcript and metadata ready. Finalizing summary...",
        )
        total_elapsed = time.time() - state.start_time
        if state.updater is not None:
            success_msg = SingleURLProgressFormatter.format_youtube_complete(
                title=video_metadata["title"],
                size_mb=video_metadata["file_size"] / (1024 * 1024),
                total_elapsed_sec=total_elapsed,
                success=True,
            )
            await state.updater.finalize(success_msg)
        elif request.mode == "interactive" and request.message is not None and not request.silent:
            await self._response_formatter.send_youtube_download_complete_notification(
                request.message,
                video_metadata["title"],
                video_metadata["resolution"],
                video_metadata["file_size"] / (1024 * 1024),
                silent=request.silent,
            )
        if state.typing_ctx is not None:
            await state.typing_ctx.__aexit__(None, None, None)

    async def finalize_error(
        self,
        *,
        state: YouTubeFeedbackState,
        error: Exception,
        correlation_id: str | None,
    ) -> None:
        if state.updater is not None:
            num_completed = len(state.completed_stages)
            failed_stage = f"Stage {num_completed + 1}/3" if num_completed < 3 else "Processing"
            error_msg = SingleURLProgressFormatter.format_youtube_complete(
                title="",
                size_mb=0,
                total_elapsed_sec=time.time() - state.start_time,
                success=False,
                error_msg=str(error),
                correlation_id=correlation_id,
                failed_stage=failed_stage,
            )
            await state.updater.finalize(error_msg)
            return
        if state.typing_ctx is not None:
            await state.typing_ctx.__aexit__(None, None, None)

    async def _draft_stage(
        self,
        *,
        request: PlatformExtractionRequest,
        text: str,
    ) -> None:
        if request.mode != "interactive" or request.silent or request.message is None:
            return
        send_message_draft = getattr(self._response_formatter, "send_message_draft", None)
        if send_message_draft is None:
            return
        await send_message_draft(request.message, text, force=False)
