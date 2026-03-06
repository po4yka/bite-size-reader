"""Status notification formatting."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.async_utils import raise_if_cancelled
from app.core.ui_strings import t

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.adapters.external.formatting.protocols import DataFormatter, ResponseSender
    from app.core.progress_tracker import ProgressTracker
    from app.core.verbosity import VerbosityResolver


class NotificationFormatterImpl:
    """Implementation of status notifications."""

    def __init__(
        self,
        response_sender: ResponseSender,
        data_formatter: DataFormatter,
        *,
        safe_reply_func: Callable[[Any, str], Awaitable[None]] | None = None,
        verbosity_resolver: VerbosityResolver | None = None,
        progress_tracker: ProgressTracker | None = None,
        lang: str = "en",
    ) -> None:
        """Initialize the notification formatter.

        Args:
            response_sender: Response sender for sending messages.
            data_formatter: Data formatter for formatting values.
            safe_reply_func: Optional callback for test compatibility.
            verbosity_resolver: Optional resolver for per-user verbosity.
                When *None*, all methods behave in DEBUG mode (legacy).
            progress_tracker: Optional tracker for editable progress messages
                used in Reader mode.
            lang: UI language code ("en" or "ru").
        """
        self._response_sender = response_sender
        self._data_formatter = data_formatter
        self._safe_reply_func = safe_reply_func
        self._verbosity_resolver = verbosity_resolver
        self._progress_tracker = progress_tracker
        self._lang = lang
        # Error notification deduplication
        self._notified_error_ids: set[str] = set()

    async def _is_reader_mode(self, message: Any) -> bool:
        """Return True when the user prefers Reader (consolidated) notifications."""
        if self._verbosity_resolver is None:
            return False  # No resolver -> DEBUG (legacy)
        from app.core.verbosity import VerbosityLevel

        return (await self._verbosity_resolver.get_verbosity(message)) == VerbosityLevel.READER

    async def _admin_log(self, text: str, *, correlation_id: str | None = None) -> None:
        """Forward *text* to the admin log chat (no-op when not configured)."""
        await self._response_sender.send_to_admin_log(text, correlation_id=correlation_id)

    async def send_help(self, message: Any) -> None:
        """Send help message to user."""
        help_text = (
            "Available Commands:\n"
            "  /start -- Welcome message and instructions\n"
            "  /help -- Show this help message\n"
            "  /summarize <URL> -- Summarize a URL\n"
            "  /summarize_all <URLs> -- Summarize multiple URLs from one message\n"
            "  /findweb <topic> -- Search the web (Firecrawl) for recent articles\n"
            "  /finddb <topic> -- Search your saved Bite-Size Reader library\n"
            "  /find <topic> -- Alias for /findweb\n"
            "  /cancel -- Cancel any pending URL or multi-link requests\n"
            "  /unread [topic] [limit] -- Show unread articles optionally filtered by topic\n"
            "  /read <ID> -- Mark article as read and view it\n"
            "  /dbinfo -- Show database overview\n"
            "  /dbverify -- Verify stored posts and required fields\n"
            "  /debug -- Toggle debug/reader notification mode\n\n"
            "Usage Tips:\n"
            "  Send URLs directly (commands are optional)\n"
            "  Forward channel posts to summarize them\n"
            "  Send /summarize and then a URL in the next message\n"
            "  Upload a .txt file with URLs (one per line) for batch processing\n"
            "  Multiple links in one message are supported\n"
            "  Use /unread [topic] [limit] to see saved articles by topic\n\n"
            "Features:\n"
            "  Structured JSON output with schema validation\n"
            "  Intelligent model fallbacks for better reliability\n"
            "  Automatic content optimization based on model capabilities\n"
            "  Silent batch processing for uploaded files\n"
            "  Progress tracking for multiple URLs"
        )
        await self._response_sender.safe_reply(message, help_text)

    async def send_welcome(self, message: Any) -> None:
        """Send welcome message to user."""
        welcome = (
            "Welcome to Bite-Size Reader!\n\n"
            "What I do:\n"
            "- Summarize articles from URLs using Firecrawl + OpenRouter.\n"
            "- Summarize forwarded channel posts.\n"
            "- Generate structured JSON summaries with reliable results.\n\n"
            "How to use:\n"
            "- Send a URL directly, or use /summarize <URL>.\n"
            "- You can also send /summarize and then the URL in the next message.\n"
            "- For forwarded posts, use /summarize_forward and then forward a channel post.\n"
            '- Multiple links in one message are supported: I will ask "Process N links?" or use /summarize_all to process immediately.\n'
            "- /dbinfo shares a quick snapshot of the internal database so you can monitor storage.\n\n"
            "Notes:\n"
            "- I reply with a strict JSON object using advanced schema validation.\n"
            "- Intelligent model selection and fallbacks ensure high success rates.\n"
            "- Errors include an Error ID you can reference in logs."
        )
        await self._response_sender.safe_reply(message, welcome)

    async def send_url_accepted_notification(
        self, message: Any, norm: str, correlation_id: str, *, silent: bool = False
    ) -> None:
        """Send URL accepted notification."""
        if silent:
            return

        try:
            from urllib.parse import urlparse

            url_domain = urlparse(norm).netloc if norm else "unknown"

            reader = await self._is_reader_mode(message)

            # Build full debug text (for admin log + Debug mode)
            debug_text = (
                f"Request Accepted\n"
                f"Domain: {url_domain}\n"
                f"URL: {norm[:60]}{'...' if len(norm) > 60 else ''}\n"
                f"Status: Fetching content...\n"
                f"Structured output with smart fallbacks"
            )

            if reader and self._progress_tracker is not None:
                user_text = t("processing_domain", self._lang).format(domain=url_domain)
            else:
                user_text = debug_text

            if reader and self._progress_tracker is not None:
                await self._progress_tracker.update(message, user_text)
            else:
                await self._response_sender.safe_reply(message, user_text)

            await self._admin_log(debug_text, correlation_id=correlation_id)
        except Exception as exc:
            raise_if_cancelled(exc)

    async def send_firecrawl_start_notification(
        self, message: Any, url: str | None = None, *, silent: bool = False
    ) -> None:
        """Send Firecrawl start notification."""
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

            if reader and self._progress_tracker is not None:
                user_text = t("extracting_content", self._lang)
            else:
                user_text = debug_text

            if reader and self._progress_tracker is not None:
                await self._progress_tracker.update(message, user_text)
            else:
                await self._response_sender.safe_reply(message, user_text)

            await self._admin_log(debug_text)
        except Exception as exc:
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
        """Send Firecrawl success notification with crawl metadata."""
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

            option_line = self._data_formatter.format_firecrawl_options(options)
            if option_line:
                lines.append(f"Options: {option_line}")

            if correlation_id:
                lines.append(f"Firecrawl CID: {correlation_id}")

            lines.append("Status: Preparing for AI analysis...")

            debug_text = "\n".join(lines)
            reader = await self._is_reader_mode(message)

            if reader and self._progress_tracker is not None:
                user_text = t("content_extracted_analyzing", self._lang).format(
                    chars=f"{excerpt_len:,}", secs=f"{latency_sec:.0f}"
                )
            else:
                user_text = debug_text

            if reader and self._progress_tracker is not None:
                await self._progress_tracker.update(message, user_text)
            else:
                await self._response_sender.safe_reply(message, user_text)

            await self._admin_log(debug_text, correlation_id=correlation_id)
        except Exception as exc:
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
        """Send content reuse notification with cached crawl metadata."""
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

            option_line = self._data_formatter.format_firecrawl_options(options)
            if option_line:
                lines.append(f"Options: {option_line}")

            if correlation_id:
                lines.append(f"Firecrawl CID: {correlation_id}")

            lines.append("Proceeding to AI analysis...")

            debug_text = "\n".join(lines)
            reader = await self._is_reader_mode(message)

            if reader and self._progress_tracker is not None:
                user_text = t("cached_content_analyzing", self._lang)
            else:
                user_text = debug_text

            if reader and self._progress_tracker is not None:
                await self._progress_tracker.update(message, user_text)
            else:
                await self._response_sender.safe_reply(message, user_text)

            await self._admin_log(debug_text, correlation_id=correlation_id)
        except Exception as exc:
            raise_if_cancelled(exc)

    async def send_cached_summary_notification(self, message: Any, *, silent: bool = False) -> None:
        """Inform the user that a cached summary is being reused."""
        if silent:
            return
        try:
            text = "Using Cached Summary\nDelivered instantly without extra processing"
            reader = await self._is_reader_mode(message)
            if reader and self._progress_tracker is not None:
                await self._progress_tracker.update(message, text)
            else:
                await self._response_sender.safe_reply(message, text)
        except Exception as exc:
            raise_if_cancelled(exc)

    async def send_html_fallback_notification(
        self, message: Any, content_len: int, *, silent: bool = False
    ) -> None:
        """Send HTML fallback notification."""
        if silent:
            return
        try:
            debug_text = (
                f"Content Processing Update\n"
                f"Markdown extraction was empty\n"
                f"Using HTML content extraction\n"
                f"Processing {content_len:,} characters...\n"
                f"Pipeline will optimize for best results"
            )

            reader = await self._is_reader_mode(message)

            if reader and self._progress_tracker is not None:
                user_text = t("processing_content", self._lang).format(chars=f"{content_len:,}")
            else:
                user_text = debug_text

            if reader and self._progress_tracker is not None:
                await self._progress_tracker.update(message, user_text)
            else:
                await self._response_sender.safe_reply(message, user_text)

            await self._admin_log(debug_text)
        except Exception as exc:
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
        """Send language detection notification."""
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
                    raise_if_cancelled(exc)

            debug_text = (
                f"Language Detection\n"
                f"{url_line}"
                f"Detected: {detected or 'unknown'}\n"
                f"Content preview:\n{content_preview}\n"
                f"Status: Preparing AI analysis with structured outputs..."
            )

            reader = await self._is_reader_mode(message)

            if reader and self._progress_tracker is not None:
                user_text = t("detected_lang_analyzing", self._lang).format(
                    lang=detected or "unknown"
                )
            else:
                user_text = debug_text

            if reader and self._progress_tracker is not None:
                await self._progress_tracker.update(message, user_text)
            else:
                await self._response_sender.safe_reply(message, user_text)

            await self._admin_log(debug_text)
        except Exception as exc:
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
        """Send content analysis notification."""
        if silent:
            return
        try:
            if enable_chunking and content_len > max_chars and (chunks or []):
                debug_text = (
                    f"Content Analysis\n"
                    f"Length: {content_len:,} characters\n"
                    f"Processing: Chunked analysis ({len(chunks or [])} chunks)\n"
                    f"Method: Advanced structured output with schema validation\n"
                    f"Status: Sending to AI model with smart fallbacks..."
                )
            elif not enable_chunking and content_len > max_chars:
                debug_text = (
                    f"Content Analysis\n"
                    f"Length: {content_len:,} characters (exceeds {max_chars:,} adaptive threshold)\n"
                    f"Processing: Single-pass (chunking disabled)\n"
                    f"Method: Structured output with intelligent fallbacks\n"
                    f"Status: Sending to AI model..."
                )
            else:
                debug_text = (
                    f"Content Analysis\n"
                    f"Length: {content_len:,} characters\n"
                    f"Processing: Single-pass summary\n"
                    f"Method: Structured output with schema validation\n"
                    f"Status: Sending to AI model..."
                )

            reader = await self._is_reader_mode(message)

            if reader and self._progress_tracker is not None:
                user_text = t("preparing_analysis", self._lang)
            else:
                user_text = debug_text

            if reader and self._progress_tracker is not None:
                await self._progress_tracker.update(message, user_text)
            else:
                await self._response_sender.safe_reply(message, user_text)

            await self._admin_log(debug_text)
        except Exception as exc:
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
        """Send LLM start notification."""
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
                    raise_if_cancelled(exc)
                    url_line = f"{url}\n" if len(url) <= 50 else f"{url[:47]}...\n"

            debug_text = (
                f"AI Analysis Starting\n"
                f"{url_line}"
                f"Model: {model}\n"
                f"Content: {content_len:,} characters\n"
                f"Mode: {structured_output_mode.upper()} with smart fallbacks\n"
                f"This may take 30-60 seconds..."
            )

            reader = await self._is_reader_mode(message)

            if reader and self._progress_tracker is not None:
                model_name = model.rsplit("/", maxsplit=1)[-1]
                user_text = t("analyzing_ai", self._lang).format(
                    model=model_name, chars=f"{content_len:,}"
                )
            else:
                user_text = debug_text

            if reader and self._progress_tracker is not None:
                await self._progress_tracker.update(message, user_text)
            else:
                await self._response_sender.safe_reply(message, user_text)

            await self._admin_log(debug_text)
        except Exception as exc:
            raise_if_cancelled(exc)

    async def send_llm_completion_notification(
        self, message: Any, llm: Any, correlation_id: str, *, silent: bool = False
    ) -> None:
        """Send LLM completion notification."""
        if silent:
            return
        try:
            model_name = llm.model or "unknown"
            latency_sec = (llm.latency_ms or 0) / 1000.0

            if llm.status == "ok":
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

                if reader and self._progress_tracker is not None:
                    user_text = t("analysis_complete", self._lang).format(secs=f"{latency_sec:.0f}")
                else:
                    user_text = debug_text

                if self._progress_tracker is not None:
                    await self._progress_tracker.update(message, user_text)
                else:
                    await self._response_sender.safe_reply(message, user_text)

                await self._admin_log(debug_text, correlation_id=correlation_id)
            else:
                # Error message for failure scenarios -- shown in both modes
                error_text = (
                    f"AI Analysis Failed\n"
                    f"Status: Error\n"
                    f"Model: {model_name}\n"
                    f"Processing time: {latency_sec:.1f}s\n"
                    f"Error: {llm.error_text or 'Unknown error'}\n"
                    f"Smart fallbacks: Active\n"
                    f"Error ID: {correlation_id}"
                )
                # Errors are always shown as standalone messages
                if self._progress_tracker is not None:
                    self._progress_tracker.clear(message)
                await self._response_sender.safe_reply(message, error_text)
                await self._admin_log(error_text, correlation_id=correlation_id)
        except Exception as exc:
            raise_if_cancelled(exc)

    async def send_forward_accepted_notification(self, message: Any, title: str) -> None:
        """Send forward request accepted notification."""
        try:
            reader = await self._is_reader_mode(message)

            debug_text = (
                "Forward Request Accepted\n"
                f"Channel: {title}\n"
                "Processing with structured outputs...\n"
                "Status: Detecting language..."
            )

            user_text = (
                t("processing_forward", self._lang).format(title=title) if reader else debug_text
            )

            if self._progress_tracker is not None:
                await self._progress_tracker.update(message, user_text)
            else:
                await self._response_sender.safe_reply(message, user_text)
        except Exception as exc:
            raise_if_cancelled(exc)

    async def send_forward_language_notification(self, message: Any, detected: str | None) -> None:
        """Send forward language detection notification."""
        try:
            reader = await self._is_reader_mode(message)

            debug_text = (
                "Language Detection\n"
                f"Detected: {detected or 'unknown'}\n"
                "Processing with structured outputs...\n"
                "Status: Sending to AI model..."
            )

            if reader:
                user_text = t("detected_lang_sending", self._lang).format(
                    lang=detected or "unknown"
                )
            else:
                user_text = debug_text

            if self._progress_tracker is not None:
                await self._progress_tracker.update(message, user_text)
            else:
                await self._response_sender.safe_reply(message, user_text)
        except Exception as exc:
            raise_if_cancelled(exc)

    async def send_forward_completion_notification(self, message: Any, llm: Any) -> None:
        """Send forward completion notification."""
        try:
            reader = await self._is_reader_mode(message)
            status_emoji = "OK" if llm.status == "ok" else "Error"
            latency_sec = (llm.latency_ms or 0) / 1000.0
            structured_info = ""
            if hasattr(llm, "structured_output_used") and llm.structured_output_used:
                mode = getattr(llm, "structured_output_mode", "unknown")

                if not reader:
                    structured_info = f"\nSchema: {mode.upper()}"

            debug_text = (
                "AI Analysis Complete\n"
                f"Status: {status_emoji}\n"
                f"Time: {latency_sec:.1f}s{structured_info}\n"
                f"Status: {'Generating summary...' if llm.status == 'ok' else 'Processing error...'}"
            )

            user_text = (
                t("ai_analysis_done", self._lang).format(secs=f"{latency_sec:.0f}")
                if reader and llm.status == "ok"
                else (t("analysis_failed", self._lang) if reader else debug_text)
            )

            if self._progress_tracker is not None:
                await self._progress_tracker.update(message, user_text)
            else:
                await self._response_sender.safe_reply(message, user_text)
        except Exception as exc:
            raise_if_cancelled(exc)

    async def send_youtube_download_notification(
        self, message: Any, url: str, *, silent: bool = False
    ) -> None:
        """Notify user that YouTube video download is starting."""
        if silent:
            return

        try:
            await self._response_sender.safe_reply(
                message,
                "YouTube Video Detected\n\n"
                "Downloading video in 1080p and extracting transcript...\n"
                "This may take a few minutes depending on video length.\n\n"
                f"URL: {url[:60]}{'...' if len(url) > 60 else ''}",
            )
        except Exception as exc:
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
        """Notify user that video download is complete."""
        if silent:
            return

        try:
            await self._response_sender.safe_reply(
                message,
                "Video Downloaded Successfully!\n\n"
                f"Title: {title[:80]}{'...' if len(title) > 80 else ''}\n"
                f"Resolution: {resolution}\n"
                f"Size: {size_mb:.1f} MB\n\n"
                "Generating summary from transcript...",
            )
        except Exception as exc:
            raise_if_cancelled(exc)

    async def send_error_notification(
        self,
        message: Any,
        error_type: str,
        correlation_id: str,
        details: str | None = None,
    ) -> None:
        """Send error notification with rich formatting."""
        if correlation_id and correlation_id in self._notified_error_ids:
            return
        if correlation_id:
            self._notified_error_ids.add(correlation_id)

        try:
            error_text, should_admin_log = self._build_error_text(
                error_type=error_type,
                correlation_id=correlation_id,
                details=details,
            )
            await self._emit_html_error(message, error_text)
            if should_admin_log:
                await self._admin_log(error_text, correlation_id=correlation_id)
        except Exception as exc:
            raise_if_cancelled(exc)

    async def _emit_html_error(self, message: Any, error_text: str) -> None:
        if self._progress_tracker is not None:
            self._progress_tracker.clear(message)
        await self._response_sender.safe_reply(message, error_text, parse_mode="HTML")

    def _build_error_text(
        self,
        *,
        error_type: str,
        correlation_id: str,
        details: str | None,
    ) -> tuple[str, bool]:
        builders = {
            "firecrawl_error": self._build_firecrawl_error_text,
            "empty_content": self._build_empty_content_error_text,
            "processing_failed": self._build_processing_failed_error_text,
            "llm_error": self._build_llm_error_text,
            "unexpected_error": self._build_unexpected_error_text,
            "timeout": self._build_timeout_error_text,
            "rate_limit": self._build_rate_limit_error_text,
            "network_error": self._build_network_error_text,
            "database_error": self._build_database_error_text,
            "access_denied": self._build_access_denied_error_text,
            "access_blocked": self._build_access_blocked_error_text,
            "message_too_long": self._build_message_too_long_error_text,
            "no_urls_found": self._build_no_urls_found_error_text,
        }
        builder = builders.get(error_type, self._build_generic_error_text)
        return builder(correlation_id=correlation_id, details=details)

    def _build_firecrawl_error_text(
        self, *, correlation_id: str, details: str | None
    ) -> tuple[str, bool]:
        _l = self._lang
        details_block = f"\n\n<i>{t('details', _l)}: {details}</i>" if details else ""
        error_text = (
            f"\u274c <b>{t('err_firecrawl_title', _l)}</b>\n\n"
            f"{t('err_firecrawl_body', _l)}\n\n"
            f"<b>{t('error_id', _l)}:</b> <code>{correlation_id}</code>"
            f"{details_block}\n\n"
            f"<b>{t('err_firecrawl_solutions', _l)}:</b>\n"
            f"\u2022 {t('err_firecrawl_hint_url', _l)}\n"
            f"\u2022 {t('err_firecrawl_hint_paywall', _l)}\n"
            f"\u2022 {t('err_firecrawl_hint_text', _l)}"
        )
        return error_text, True

    def _build_empty_content_error_text(
        self, *, correlation_id: str, details: str | None
    ) -> tuple[str, bool]:
        _l = self._lang
        error_text = (
            f"\u274c <b>{t('err_empty_title', _l)}</b>\n\n"
            f"{t('err_empty_body', _l)}\n\n"
            f"<b>{t('err_empty_causes', _l)}:</b>\n"
            f"\u2022 {t('err_empty_cause_block', _l)}\n"
            f"\u2022 {t('err_empty_cause_paywall', _l)}\n"
            f"\u2022 {t('err_empty_cause_nontext', _l)}\n"
            f"\u2022 {t('err_empty_cause_server', _l)}\n\n"
            f"<b>{t('err_empty_suggestions', _l)}:</b>\n"
            f"\u2022 {t('err_empty_hint_url', _l)}\n"
            f"\u2022 {t('err_empty_hint_private', _l)}\n\n"
            f"<b>{t('error_id', _l)}:</b> <code>{correlation_id}</code>"
        )
        return error_text, True

    def _build_processing_failed_error_text(
        self, *, correlation_id: str, details: str | None
    ) -> tuple[str, bool]:
        _l = self._lang
        detail_block = f"\n\n<i>{t('reason', _l)}: {details}</i>" if details else ""
        error_text = (
            f"\u2699\ufe0f <b>{t('err_processing_title', _l)}</b>\n\n"
            f"{t('err_processing_body', _l)}\n\n"
            f"<b>{t('err_processing_what', _l)}:</b>\n"
            f"\u2022 {t('err_processing_parse', _l)}\n"
            f"\u2022 {t('err_processing_repair', _l)}\n\n"
            f"<b>{t('err_processing_try', _l)}:</b>\n"
            f"\u2022 {t('err_processing_hint_retry', _l)}\n"
            f"\u2022 {t('err_processing_hint_other', _l)}\n\n"
            f"<b>{t('error_id', _l)}:</b> <code>{correlation_id}</code>{detail_block}"
        )
        return error_text, True

    def _build_llm_error_text(
        self, *, correlation_id: str, details: str | None
    ) -> tuple[str, bool]:
        _l = self._lang
        models_info = ""
        error_info = details or ""
        if "Tried" in error_info and "model(s):" in error_info:
            lines = error_info.split("\n")
            models_info = f"\n\u2022 {lines[0]}" if lines else ""
            error_detail = "\n".join(lines[1:]) if len(lines) > 1 else ""
        else:
            error_detail = f"\n\n<i>Provider response: {details}</i>" if details else ""

        error_text = f"\U0001f916 <b>{t('err_llm_title', _l)}</b>\n\n{t('err_llm_body', _l)}"
        if models_info:
            error_text += f"\n\n<b>{t('err_llm_models', _l)}:</b>{models_info}"
        error_text += (
            f"\n\n<b>{t('err_llm_solutions', _l)}:</b>\n"
            f"\u2022 {t('err_llm_hint_retry', _l)}\n"
            f"\u2022 {t('err_llm_hint_complex', _l)}\n"
            f"\u2022 {t('err_llm_hint_support', _l)}\n\n"
            f"<b>{t('error_id', _l)}:</b> <code>{correlation_id}</code>"
        )
        if error_detail:
            error_text += error_detail
        return error_text, True

    def _build_unexpected_error_text(
        self, *, correlation_id: str, details: str | None
    ) -> tuple[str, bool]:
        _l = self._lang
        details_block = f"\n\n<i>{t('details', _l)}: {details}</i>" if details else ""
        error_text = (
            f"\u26a0\ufe0f <b>{t('err_unexpected_title', _l)}</b>\n\n"
            f"{t('err_unexpected_body', _l)}\n\n"
            f"<b>{t('error_id', _l)}:</b> <code>{correlation_id}</code>\n"
            f"<b>{t('status', _l)}:</b> {t('err_unexpected_status', _l)}"
            f"{details_block}"
        )
        return error_text, True

    def _build_timeout_error_text(
        self, *, correlation_id: str, details: str | None
    ) -> tuple[str, bool]:
        _l = self._lang
        error_text = (
            f"\u23f1 <b>{t('err_timeout_title', _l)}</b>\n\n"
            f"{details or t('err_timeout_default', _l)}\n\n"
            f"<b>{t('err_timeout_try', _l)}:</b>\n"
            f"\u2022 {t('err_timeout_hint_smaller', _l)}\n"
            f"\u2022 {t('err_timeout_hint_wait', _l)}\n\n"
            f"<b>{t('error_id', _l)}:</b> <code>{correlation_id}</code>"
        )
        return error_text, True

    def _build_rate_limit_error_text(
        self, *, correlation_id: str, details: str | None
    ) -> tuple[str, bool]:
        _l = self._lang
        error_text = (
            f"\u23f3 <b>{t('err_rate_limit_title', _l)}</b>\n\n"
            f"{details or t('err_rate_limit_default', _l)}\n\n"
            f"<b>{t('status', _l)}:</b> {t('err_rate_limit_status', _l)}\n\n"
            f"<b>{t('error_id', _l)}:</b> <code>{correlation_id}</code>"
        )
        return error_text, True

    def _build_network_error_text(
        self, *, correlation_id: str, details: str | None
    ) -> tuple[str, bool]:
        _l = self._lang
        error_text = (
            f"\U0001f310 <b>{t('err_network_title', _l)}</b>\n\n"
            f"{details or t('err_network_default', _l)}\n\n"
            f"<b>{t('err_network_try', _l)}:</b>\n"
            f"\u2022 {t('err_network_hint_conn', _l)}\n"
            f"\u2022 {t('err_network_hint_retry', _l)}\n\n"
            f"<b>{t('error_id', _l)}:</b> <code>{correlation_id}</code>"
        )
        return error_text, True

    def _build_database_error_text(
        self, *, correlation_id: str, details: str | None
    ) -> tuple[str, bool]:
        _l = self._lang
        error_text = (
            f"\U0001f4be <b>{t('err_database_title', _l)}</b>\n\n"
            f"{details or t('err_database_default', _l)}\n\n"
            f"<b>{t('status', _l)}:</b> {t('err_database_status', _l)}\n\n"
            f"<b>{t('error_id', _l)}:</b> <code>{correlation_id}</code>"
        )
        return error_text, True

    def _build_access_denied_error_text(
        self, *, correlation_id: str, details: str | None
    ) -> tuple[str, bool]:
        _l = self._lang
        error_text = (
            f"\U0001f6d1 <b>{t('err_access_denied_title', _l)}</b>\n\n"
            f"{t('err_access_denied_body', _l).format(uid=details or 'unknown')}\n\n"
            f"{t('err_access_denied_contact', _l)}"
        )
        return error_text, False

    def _build_access_blocked_error_text(
        self, *, correlation_id: str, details: str | None
    ) -> tuple[str, bool]:
        _l = self._lang
        error_text = (
            f"\U0001f6ab <b>{t('err_access_blocked_title', _l)}</b>\n\n"
            f"{details or t('err_access_blocked_default', _l)}\n\n"
            f"<b>{t('status', _l)}:</b> {t('err_access_blocked_status', _l)}"
        )
        return error_text, False

    def _build_message_too_long_error_text(
        self, *, correlation_id: str, details: str | None
    ) -> tuple[str, bool]:
        _l = self._lang
        error_text = (
            f"\U0001f4cf <b>{t('err_message_too_long_title', _l)}</b>\n\n"
            f"{details or t('err_message_too_long_default', _l)}\n\n"
            f"<b>{t('suggestions', _l)}:</b>\n"
            f"\u2022 {t('err_message_too_long_hint_split', _l)}\n"
            f"\u2022 {t('err_message_too_long_hint_file', _l)}"
        )
        return error_text, False

    def _build_no_urls_found_error_text(
        self, *, correlation_id: str, details: str | None
    ) -> tuple[str, bool]:
        _l = self._lang
        error_text = (
            f"\U0001f517 <b>{t('err_no_urls_title', _l)}</b>\n\n"
            f"{details or t('err_no_urls_default', _l)}\n\n"
            f"<b>{t('try_label', _l)}:</b>\n"
            f"\u2022 {t('err_no_urls_hint_http', _l)}\n"
            f"\u2022 {t('err_no_urls_hint_typo', _l)}"
        )
        return error_text, False

    def _build_generic_error_text(
        self, *, correlation_id: str, details: str | None
    ) -> tuple[str, bool]:
        _l = self._lang
        error_text = (
            f"<b>{t('err_generic_title', _l)}</b>\n"
            f"{details or t('err_generic_default', _l)}\n\n"
            f"<b>{t('error_id', _l)}:</b> <code>{correlation_id}</code>"
        )
        return error_text, True
