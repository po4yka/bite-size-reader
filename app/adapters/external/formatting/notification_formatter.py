"""Status notification formatting."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.adapters.external.formatting.notification_context import NotificationFormatterContext
from app.adapters.external.formatting.notification_errors import NotificationErrorPresenter
from app.adapters.external.formatting.notification_onboarding import (
    NotificationOnboardingPresenter,
)
from app.adapters.external.formatting.notification_pipeline import NotificationPipelinePresenter

if TYPE_CHECKING:
    from app.adapters.external.formatting.protocols import DataFormatter, ResponseSender
    from app.core.telegram_progress_message import TelegramProgressMessage
    from app.core.verbosity import VerbosityResolver


class NotificationFormatterImpl:
    """Implementation of status notifications."""

    def __init__(
        self,
        response_sender: ResponseSender,
        data_formatter: DataFormatter,
        *,
        verbosity_resolver: VerbosityResolver | None = None,
        progress_tracker: TelegramProgressMessage | None = None,
        lang: str = "en",
    ) -> None:
        self._context = NotificationFormatterContext(
            response_sender=response_sender,
            data_formatter=data_formatter,
            verbosity_resolver=verbosity_resolver,
            progress_tracker=progress_tracker,
            lang=lang,
        )
        self._onboarding = NotificationOnboardingPresenter(self._context)
        self._pipeline = NotificationPipelinePresenter(self._context)
        self._errors = NotificationErrorPresenter(self._context)

    async def send_help(self, message: Any) -> None:
        await self._onboarding.send_help(message)

    async def send_welcome(self, message: Any) -> None:
        await self._onboarding.send_welcome(message)

    async def send_url_accepted_notification(
        self, message: Any, norm: str, correlation_id: str, *, silent: bool = False
    ) -> None:
        await self._pipeline.send_url_accepted_notification(
            message,
            norm,
            correlation_id,
            silent=silent,
        )

    async def send_firecrawl_start_notification(
        self, message: Any, url: str | None = None, *, silent: bool = False
    ) -> None:
        await self._pipeline.send_firecrawl_start_notification(message, url=url, silent=silent)

    async def send_firecrawl_success_notification(
        self,
        message: Any,
        excerpt_len: int,
        latency_sec: float,
        *,
        http_status: int | None = None,
        crawl_status: str | None = None,
        correlation_id: str | None = None,
        endpoint: str | None = None,
        options: dict[str, Any] | None = None,
        silent: bool = False,
    ) -> None:
        await self._pipeline.send_firecrawl_success_notification(
            message,
            excerpt_len,
            latency_sec,
            http_status=http_status,
            crawl_status=crawl_status,
            correlation_id=correlation_id,
            endpoint=endpoint,
            options=options,
            silent=silent,
        )

    async def send_content_reuse_notification(
        self,
        message: Any,
        *,
        http_status: int | None = None,
        crawl_status: str | None = None,
        latency_sec: float | None = None,
        correlation_id: str | None = None,
        options: dict[str, Any] | None = None,
        silent: bool = False,
    ) -> None:
        await self._pipeline.send_content_reuse_notification(
            message,
            http_status=http_status,
            crawl_status=crawl_status,
            latency_sec=latency_sec,
            correlation_id=correlation_id,
            options=options,
            silent=silent,
        )

    async def send_cached_summary_notification(self, message: Any, *, silent: bool = False) -> None:
        await self._pipeline.send_cached_summary_notification(message, silent=silent)

    async def send_html_fallback_notification(
        self, message: Any, content_len: int, *, silent: bool = False
    ) -> None:
        await self._pipeline.send_html_fallback_notification(
            message,
            content_len,
            silent=silent,
        )

    async def send_language_detection_notification(
        self,
        message: Any,
        detected: str | None,
        content_preview: str,
        *,
        url: str | None = None,
        silent: bool = False,
    ) -> None:
        await self._pipeline.send_language_detection_notification(
            message,
            detected,
            content_preview,
            url=url,
            silent=silent,
        )

    async def send_content_analysis_notification(
        self,
        message: Any,
        content_len: int,
        max_chars: int,
        enable_chunking: bool,
        chunks: list[str] | None,
        structured_output_mode: str,
        *,
        silent: bool = False,
    ) -> None:
        await self._pipeline.send_content_analysis_notification(
            message,
            content_len,
            max_chars,
            enable_chunking,
            chunks,
            structured_output_mode,
            silent=silent,
        )

    async def send_llm_start_notification(
        self,
        message: Any,
        model: str,
        content_len: int,
        structured_output_mode: str,
        *,
        url: str | None = None,
        silent: bool = False,
    ) -> None:
        await self._pipeline.send_llm_start_notification(
            message,
            model,
            content_len,
            structured_output_mode,
            url=url,
            silent=silent,
        )

    async def send_llm_completion_notification(
        self, message: Any, llm: Any, correlation_id: str, *, silent: bool = False
    ) -> None:
        await self._pipeline.send_llm_completion_notification(
            message,
            llm,
            correlation_id,
            silent=silent,
        )

    async def send_forward_accepted_notification(self, message: Any, title: str) -> None:
        await self._pipeline.send_forward_accepted_notification(message, title)

    async def send_forward_language_notification(self, message: Any, detected: str | None) -> None:
        await self._pipeline.send_forward_language_notification(message, detected)

    async def send_forward_completion_notification(self, message: Any, llm: Any) -> None:
        await self._pipeline.send_forward_completion_notification(message, llm)

    async def send_youtube_download_notification(
        self, message: Any, url: str, *, silent: bool = False
    ) -> None:
        await self._pipeline.send_youtube_download_notification(message, url, silent=silent)

    async def send_youtube_download_complete_notification(
        self,
        message: Any,
        title: str,
        resolution: str,
        size_mb: float,
        *,
        silent: bool = False,
    ) -> None:
        await self._pipeline.send_youtube_download_complete_notification(
            message,
            title,
            resolution,
            size_mb,
            silent=silent,
        )

    async def send_error_notification(
        self,
        message: Any,
        error_type: str,
        correlation_id: str,
        details: str | None = None,
    ) -> None:
        await self._errors.send_error_notification(
            message,
            error_type,
            correlation_id,
            details=details,
        )
