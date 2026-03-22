"""Pipeline-status notification presenters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.async_utils import raise_if_cancelled
from app.core.call_status import CallStatus
from app.core.logging_utils import get_logger
from app.core.ui_strings import t

if TYPE_CHECKING:
    from .notification_context import NotificationFormatterContext

logger = get_logger(__name__)


class NotificationPipelinePresenter:
    """Handle reader/debug dispatch and non-error status notifications."""

    def __init__(self, context: NotificationFormatterContext) -> None:
        self._context = context

    async def _is_reader_mode(self, message: Any) -> bool:
        if self._context.verbosity_resolver is None:
            return False
        from app.core.verbosity import VerbosityLevel

        return (
            await self._context.verbosity_resolver.get_verbosity(message)
        ) == VerbosityLevel.READER

    async def _admin_log(self, text: str, *, correlation_id: str | None = None) -> None:
        await self._context.response_sender.send_to_admin_log(text, correlation_id=correlation_id)

    async def _dispatch(
        self,
        message: Any,
        debug_text: str,
        user_text: str,
        *,
        correlation_id: str | None = None,
    ) -> None:
        reader = await self._is_reader_mode(message)
        if reader and self._context.progress_tracker is not None:
            await self._context.progress_tracker.update(message, user_text)
        else:
            await self._context.response_sender.safe_reply(message, user_text)
        await self._admin_log(debug_text, correlation_id=correlation_id)

    async def send_url_accepted_notification(
        self, message: Any, norm: str, correlation_id: str, *, silent: bool = False
    ) -> None:
        if silent:
            return
        try:
            from urllib.parse import urlparse

            url_domain = urlparse(norm).netloc if norm else "unknown"
            reader = await self._is_reader_mode(message)
            debug_text = (
                f"Request Accepted\n"
                f"Domain: {url_domain}\n"
                f"URL: {norm[:60]}{'...' if len(norm) > 60 else ''}\n"
                f"Status: Fetching content...\n"
                f"Structured output with smart fallbacks"
            )
            user_text = (
                t("processing_domain", self._context.lang).format(domain=url_domain)
                if reader and self._context.progress_tracker is not None
                else debug_text
            )
            await self._dispatch(message, debug_text, user_text, correlation_id=correlation_id)
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)

    async def send_firecrawl_start_notification(
        self, message: Any, url: str | None = None, *, silent: bool = False
    ) -> None:
        if silent:
            return
        try:
            url_display = ""
            if url:
                url_display = f"\n{url[:57]}..." if len(url) > 60 else f"\n{url}"
            reader = await self._is_reader_mode(message)
            debug_text = (
                f"Firecrawl Extraction{url_display}\n"
                "Connecting to Firecrawl API...\n"
                "This may take 10-30 seconds\n"
                "Processing pipeline active"
            )
            user_text = (
                t("extracting_content", self._context.lang)
                if reader and self._context.progress_tracker is not None
                else debug_text
            )
            await self._dispatch(message, debug_text, user_text)
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)

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
        if silent:
            return
        try:
            lines = [
                "Content Extracted Successfully",
                f"Size: ~{excerpt_len:,} characters",
                f"Extraction time: {latency_sec:.1f}s",
            ]
            status_bits: list[str] = []
            if http_status is not None:
                status_bits.append(f"HTTP {http_status}")
            if crawl_status:
                status_bits.append(crawl_status)
            if status_bits:
                lines.append("Firecrawl: " + " | ".join(status_bits))
            if endpoint:
                lines.append(f"Endpoint: {endpoint}")
            option_line = self._context.data_formatter.format_firecrawl_options(options)
            if option_line:
                lines.append(f"Options: {option_line}")
            if correlation_id:
                lines.append(f"Firecrawl CID: {correlation_id}")
            lines.append("Status: Preparing for AI analysis...")

            debug_text = "\n".join(lines)
            reader = await self._is_reader_mode(message)
            user_text = (
                t("content_extracted_analyzing", self._context.lang).format(
                    chars=f"{excerpt_len:,}",
                    secs=f"{latency_sec:.0f}",
                )
                if reader and self._context.progress_tracker is not None
                else debug_text
            )
            await self._dispatch(message, debug_text, user_text, correlation_id=correlation_id)
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)

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
        if silent:
            return
        try:
            lines = [
                "Reusing Cached Content",
                "Status: Content already extracted",
            ]
            status_bits: list[str] = []
            if http_status is not None:
                status_bits.append(f"HTTP {http_status}")
            if crawl_status:
                status_bits.append(crawl_status)
            if status_bits:
                lines.append("Firecrawl (cached): " + " | ".join(status_bits))
            if latency_sec is not None:
                lines.append(f"Original extraction: {latency_sec:.1f}s")
            option_line = self._context.data_formatter.format_firecrawl_options(options)
            if option_line:
                lines.append(f"Options: {option_line}")
            if correlation_id:
                lines.append(f"Firecrawl CID: {correlation_id}")
            lines.append("Proceeding to AI analysis...")
            debug_text = "\n".join(lines)
            reader = await self._is_reader_mode(message)
            user_text = (
                t("cached_content_analyzing", self._context.lang)
                if reader and self._context.progress_tracker is not None
                else debug_text
            )
            await self._dispatch(message, debug_text, user_text, correlation_id=correlation_id)
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)

    async def send_cached_summary_notification(self, message: Any, *, silent: bool = False) -> None:
        if silent:
            return
        try:
            text = "Using Cached Summary\nDelivered instantly without extra processing"
            reader = await self._is_reader_mode(message)
            if reader and self._context.progress_tracker is not None:
                await self._context.progress_tracker.update(message, text)
            else:
                await self._context.response_sender.safe_reply(message, text)
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)

    async def send_html_fallback_notification(
        self, message: Any, content_len: int, *, silent: bool = False
    ) -> None:
        if silent:
            return
        try:
            debug_text = (
                "Content Processing Update\n"
                "Markdown extraction was empty\n"
                "Using HTML content extraction\n"
                f"Processing {content_len:,} characters...\n"
                "Pipeline will optimize for best results"
            )
            reader = await self._is_reader_mode(message)
            user_text = (
                t("processing_content", self._context.lang).format(chars=f"{content_len:,}")
                if reader and self._context.progress_tracker is not None
                else debug_text
            )
            await self._dispatch(message, debug_text, user_text)
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)

    async def send_language_detection_notification(
        self,
        message: Any,
        detected: str | None,
        content_preview: str,
        *,
        url: str | None = None,
        silent: bool = False,
    ) -> None:
        if silent:
            return
        try:
            url_line = ""
            if url:
                try:
                    from urllib.parse import urlparse

                    parsed = urlparse(url)
                    domain = parsed.netloc or parsed.path.split("/")[0] if parsed.path else url
                    if domain.startswith("www."):
                        domain = domain[4:]
                    if domain and len(domain) <= 40:
                        url_line = f"Source: {domain}\n"
                except Exception as exc:
                    logger.debug("notification_send_failed", extra={"error": str(exc)})
                    raise_if_cancelled(exc)

            debug_text = (
                "Language Detection\n"
                f"{url_line}"
                f"Detected: {detected or 'unknown'}\n"
                f"Content preview:\n{content_preview}\n"
                "Status: Preparing AI analysis with structured outputs..."
            )
            reader = await self._is_reader_mode(message)
            user_text = (
                t("detected_lang_analyzing", self._context.lang).format(lang=detected or "unknown")
                if reader and self._context.progress_tracker is not None
                else debug_text
            )
            await self._dispatch(message, debug_text, user_text)
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)

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
        _ = structured_output_mode
        if silent:
            return
        try:
            if enable_chunking and content_len > max_chars and (chunks or []):
                debug_text = (
                    "Content Analysis\n"
                    f"Length: {content_len:,} characters\n"
                    f"Processing: Chunked analysis ({len(chunks or [])} chunks)\n"
                    "Method: Advanced structured output with schema validation\n"
                    "Status: Sending to AI model with smart fallbacks..."
                )
            elif not enable_chunking and content_len > max_chars:
                debug_text = (
                    "Content Analysis\n"
                    f"Length: {content_len:,} characters (exceeds {max_chars:,} adaptive threshold)\n"
                    "Processing: Single-pass (chunking disabled)\n"
                    "Method: Structured output with intelligent fallbacks\n"
                    "Status: Sending to AI model..."
                )
            else:
                debug_text = (
                    "Content Analysis\n"
                    f"Length: {content_len:,} characters\n"
                    "Processing: Single-pass summary\n"
                    "Method: Structured output with schema validation\n"
                    "Status: Sending to AI model..."
                )
            reader = await self._is_reader_mode(message)
            user_text = (
                t("preparing_analysis", self._context.lang)
                if reader and self._context.progress_tracker is not None
                else debug_text
            )
            await self._dispatch(message, debug_text, user_text)
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)

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
        if silent:
            return
        try:
            url_line = ""
            if url:
                try:
                    from urllib.parse import urlparse

                    parsed = urlparse(url)
                    domain = parsed.netloc or parsed.path.split("/")[0] if parsed.path else url
                    if domain.startswith("www."):
                        domain = domain[4:]
                    if domain and len(domain) <= 40:
                        url_line = f"Source: {domain}\n"
                    elif len(url) <= 50:
                        url_line = f"{url}\n"
                    else:
                        url_line = f"{url[:47]}...\n"
                except Exception as exc:
                    logger.debug("notification_send_failed", extra={"error": str(exc)})
                    raise_if_cancelled(exc)
                    url_line = f"{url}\n" if len(url) <= 50 else f"{url[:47]}...\n"
            debug_text = (
                "AI Analysis Starting\n"
                f"{url_line}"
                f"Model: {model}\n"
                f"Content: {content_len:,} characters\n"
                f"Mode: {structured_output_mode.upper()} with smart fallbacks\n"
                "This may take 30-60 seconds..."
            )
            reader = await self._is_reader_mode(message)
            user_text = (
                t("analyzing_ai", self._context.lang).format(
                    model=model.rsplit("/", maxsplit=1)[-1],
                    chars=f"{content_len:,}",
                )
                if reader and self._context.progress_tracker is not None
                else debug_text
            )
            await self._dispatch(message, debug_text, user_text)
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)

    async def send_llm_completion_notification(
        self, message: Any, llm: Any, correlation_id: str, *, silent: bool = False
    ) -> None:
        if silent:
            return
        try:
            model_name = llm.model or "unknown"
            latency_sec = (llm.latency_ms or 0) / 1000.0
            if llm.status == CallStatus.OK:
                prompt_tokens = llm.tokens_prompt or 0
                completion_tokens = llm.tokens_completion or 0
                tokens_used = prompt_tokens + completion_tokens
                lines = [
                    "AI Analysis Complete",
                    "Status: Success",
                    f"Model: {model_name}",
                    f"Processing time: {latency_sec:.1f}s",
                    (
                        "Tokens -- prompt: "
                        f"{prompt_tokens:,} / completion: {completion_tokens:,} "
                        f"(total: {tokens_used:,})"
                    ),
                ]
                if llm.cost_usd is not None:
                    lines.append(f"Estimated cost: ${llm.cost_usd:.4f}")
                if getattr(llm, "structured_output_used", False):
                    mode = getattr(llm, "structured_output_mode", "unknown")
                    lines.append(f"Structured output: {mode.upper()}")
                if llm.endpoint:
                    lines.append(f"Endpoint: {llm.endpoint}")
                if correlation_id:
                    lines.append(f"Request ID: {correlation_id}")
                lines.append("Status: Generating summary...")
                debug_text = "\n".join(lines)
                reader = await self._is_reader_mode(message)
                user_text = (
                    t("analysis_complete", self._context.lang).format(secs=f"{latency_sec:.0f}")
                    if reader and self._context.progress_tracker is not None
                    else debug_text
                )
                if self._context.progress_tracker is not None:
                    await self._context.progress_tracker.update(message, user_text)
                else:
                    await self._context.response_sender.safe_reply(message, user_text)
                await self._admin_log(debug_text, correlation_id=correlation_id)
                return

            error_text = (
                "AI Analysis Failed\n"
                "Status: Error\n"
                f"Model: {model_name}\n"
                f"Processing time: {latency_sec:.1f}s\n"
                f"Error: {llm.error_text or 'Unknown error'}\n"
                "Smart fallbacks: Active\n"
                f"Error ID: {correlation_id}"
            )
            if self._context.progress_tracker is not None:
                self._context.progress_tracker.clear(message)
            await self._context.response_sender.safe_reply(message, error_text)
            await self._admin_log(error_text, correlation_id=correlation_id)
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)

    async def send_forward_accepted_notification(self, message: Any, title: str) -> None:
        try:
            reader = await self._is_reader_mode(message)
            debug_text = (
                "Forward Request Accepted\n"
                f"Channel: {title}\n"
                "Processing with structured outputs...\n"
                "Status: Detecting language..."
            )
            user_text = (
                t("processing_forward", self._context.lang).format(title=title)
                if reader
                else debug_text
            )
            if self._context.progress_tracker is not None:
                await self._context.progress_tracker.update(message, user_text)
            else:
                await self._context.response_sender.safe_reply(message, user_text)
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)

    async def send_forward_language_notification(self, message: Any, detected: str | None) -> None:
        try:
            reader = await self._is_reader_mode(message)
            debug_text = (
                "Language Detection\n"
                f"Detected: {detected or 'unknown'}\n"
                "Processing with structured outputs...\n"
                "Status: Sending to AI model..."
            )
            user_text = (
                t("detected_lang_sending", self._context.lang).format(lang=detected or "unknown")
                if reader
                else debug_text
            )
            if self._context.progress_tracker is not None:
                await self._context.progress_tracker.update(message, user_text)
            else:
                await self._context.response_sender.safe_reply(message, user_text)
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)

    async def send_forward_completion_notification(self, message: Any, llm: Any) -> None:
        try:
            reader = await self._is_reader_mode(message)
            status_emoji = "OK" if llm.status == CallStatus.OK else "Error"
            latency_sec = (llm.latency_ms or 0) / 1000.0
            structured_info = ""
            if getattr(llm, "structured_output_used", False) and not reader:
                mode = getattr(llm, "structured_output_mode", "unknown")
                structured_info = f"\nSchema: {mode.upper()}"
            debug_text = (
                "AI Analysis Complete\n"
                f"Status: {status_emoji}\n"
                f"Time: {latency_sec:.1f}s{structured_info}\n"
                f"Status: {'Generating summary...' if llm.status == 'ok' else 'Processing error...'}"
            )
            user_text = (
                t("ai_analysis_done", self._context.lang).format(secs=f"{latency_sec:.0f}")
                if reader and llm.status == CallStatus.OK
                else (t("analysis_failed", self._context.lang) if reader else debug_text)
            )
            if self._context.progress_tracker is not None:
                await self._context.progress_tracker.update(message, user_text)
            else:
                await self._context.response_sender.safe_reply(message, user_text)
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)

    async def send_youtube_download_notification(
        self, message: Any, url: str, *, silent: bool = False
    ) -> None:
        if silent:
            return
        try:
            await self._context.response_sender.safe_reply(
                message,
                "YouTube Video Detected\n\n"
                "Downloading video in 1080p and extracting transcript...\n"
                "This may take a few minutes depending on video length.\n\n"
                f"URL: {url[:60]}{'...' if len(url) > 60 else ''}",
            )
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)

    async def send_youtube_download_complete_notification(
        self,
        message: Any,
        title: str,
        resolution: str,
        size_mb: float,
        *,
        silent: bool = False,
    ) -> None:
        if silent:
            return
        try:
            await self._context.response_sender.safe_reply(
                message,
                "Video Downloaded Successfully!\n\n"
                f"Title: {title[:80]}{'...' if len(title) > 80 else ''}\n"
                f"Resolution: {resolution}\n"
                f"Size: {size_mb:.1f} MB\n\n"
                "Generating summary from transcript...",
            )
        except Exception as exc:
            logger.debug("notification_send_failed", extra={"error": str(exc)})
            raise_if_cancelled(exc)
