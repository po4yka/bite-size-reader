"""Status notification formatting."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.async_utils import raise_if_cancelled

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.adapters.external.formatting.data_formatter import DataFormatterImpl
    from app.adapters.external.formatting.response_sender import ResponseSenderImpl
    from app.core.progress_tracker import ProgressTracker
    from app.core.verbosity import VerbosityResolver


class NotificationFormatterImpl:
    """Implementation of status notifications."""

    def __init__(
        self,
        response_sender: ResponseSenderImpl,
        data_formatter: DataFormatterImpl,
        *,
        safe_reply_func: Callable[[Any, str], Awaitable[None]] | None = None,
        verbosity_resolver: VerbosityResolver | None = None,
        progress_tracker: ProgressTracker | None = None,
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
        """
        self._response_sender = response_sender
        self._data_formatter = data_formatter
        self._safe_reply_func = safe_reply_func
        self._verbosity_resolver = verbosity_resolver
        self._progress_tracker = progress_tracker
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
                user_text = f"Processing {url_domain}..."
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
                user_text = "Extracting content..."
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
                user_text = (
                    f"Content extracted ({excerpt_len:,} chars, {latency_sec:.0f}s). Analyzing..."
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
                user_text = "Using cached content. Analyzing..."
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
                user_text = f"Processing content ({content_len:,} chars)..."
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
                user_text = f"Detected language: {detected or 'unknown'}. Analyzing..."
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
                user_text = "Preparing AI analysis..."
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
                user_text = "Analyzing with AI..."
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
                    user_text = f"Analysis complete ({latency_sec:.0f}s). Generating summary..."
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

            user_text = f"Processing forwarded post from {title}..." if reader else debug_text

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
                user_text = f"Detected language: {detected or 'unknown'}. Sending to model..."
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
                f"AI analysis done ({latency_sec:.0f}s). Generating summary..."
                if reader and llm.status == "ok"
                else ("AI analysis failed. See details above." if reader else debug_text)
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
        # Deduplication: check if we've already sent a notification for this error ID
        if correlation_id and correlation_id in self._notified_error_ids:
            return

        # Mark this error ID as notified
        if correlation_id:
            self._notified_error_ids.add(correlation_id)

        try:

            async def _emit(text: str) -> None:
                # Errors always use safe_reply (standalone messages in both modes)
                if self._progress_tracker is not None:
                    self._progress_tracker.clear(message)
                await self._response_sender.safe_reply(message, text)

            if error_type == "firecrawl_error":
                details_block = f"\n\n{details}" if details else ""
                error_text = (
                    "Content Extraction Failed\n"
                    "Unable to extract readable content\n"
                    f"Error ID: {correlation_id}"
                    f"{details_block}\n\n"
                    "Possible Solutions:\n"
                    "- Try a different URL\n"
                    "- Check if content is publicly accessible\n"
                    "- Ensure URL points to text-based content"
                )
                await _emit(error_text)
                await self._admin_log(error_text, correlation_id=correlation_id)
            elif error_type == "empty_content":
                error_text = (
                    f"Content Extraction Failed\n\n"
                    f"Possible Causes:\n"
                    f"- Website blocking automated access\n"
                    f"- Content behind paywall/login\n"
                    f"- Non-text content (images, videos)\n"
                    f"- Temporary server issues\n"
                    f"- Invalid or inaccessible URL\n\n"
                    f"Suggestions:\n"
                    f"- Try a different URL\n"
                    f"- Check if content is publicly accessible\n"
                    f"- Ensure URL points to text-based content\n\n"
                    f"Error ID: {correlation_id}"
                )
                await _emit(error_text)
                await self._admin_log(error_text, correlation_id=correlation_id)
            elif error_type == "processing_failed":
                detail_block = f"\nReason: {details}" if details else ""
                if self._safe_reply_func is not None:
                    await self._safe_reply_func(
                        message,
                        f"Invalid summary format. Error ID: {correlation_id}{detail_block}",
                    )
                else:
                    message_parts = [
                        "Processing Failed",
                        f"Invalid summary format despite smart fallbacks{detail_block}",
                        "",
                        "What happened:",
                        "- The AI models returned data that couldn't be processed",
                        "- All automatic repair attempts were unsuccessful",
                        "",
                        "Try:",
                        "- Submit the URL again",
                        "- Try a different article from the same source",
                        "",
                        f"Error ID: {correlation_id}",
                    ]
                    error_text = "\n".join(message_parts)
                    await _emit(error_text)
                    await self._admin_log(error_text, correlation_id=correlation_id)
            elif error_type == "llm_error":
                models_info = ""
                error_info = details or ""

                if "Tried" in error_info and "model(s):" in error_info:
                    lines = error_info.split("\n")
                    models_info = lines[0] if lines else ""
                    error_detail = "\n".join(lines[1:]) if len(lines) > 1 else ""
                else:
                    error_detail = f"\nProvider response: {details}" if details else ""

                message_parts = [
                    "Processing Failed",
                    "All AI models failed despite automatic fallbacks",
                ]

                if models_info:
                    message_parts.append(models_info)

                if error_detail:
                    message_parts.append(error_detail)

                message_parts.extend(
                    [
                        "",
                        "Possible Solutions:",
                        "- Check your account balance/credits",
                        "- Try again in a few moments",
                        "- Contact support if the issue persists",
                        "",
                        f"Error ID: {correlation_id}",
                    ]
                )
                error_text = "\n".join(message_parts)
                await _emit(error_text)
                await self._admin_log(error_text, correlation_id=correlation_id)
            else:
                # Generic error
                error_text = (
                    f"Error Occurred\n{details or 'Unknown error'}\nError ID: {correlation_id}"
                )
                await _emit(error_text)
                await self._admin_log(error_text, correlation_id=correlation_id)
        except Exception as exc:
            raise_if_cancelled(exc)
