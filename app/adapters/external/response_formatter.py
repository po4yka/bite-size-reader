"""Response formatting facade.

This module provides the ResponseFormatter class, which serves as a facade for
the decomposed formatting components. It maintains backward compatibility with
existing code while delegating to specialized components:

- DataFormatterImpl: Stateless data formatting (bytes, metrics, stats)
- MessageValidatorImpl: Security validation (content safety, URL validation, rate limiting)
- ResponseSenderImpl: Core Telegram sending (safe_reply, edit_message, reply_json)
- TextProcessorImpl: Text processing (chunking, sanitization, slugify)
- NotificationFormatterImpl: Status notifications (20+ notification methods)
- SummaryPresenterImpl: Summary presentation (structured summaries, translations)
- DatabasePresenterImpl: Database UI (overview, verification, search results)

All public methods are delegated to the appropriate component while maintaining
the original API signatures for backward compatibility.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.adapters.external.formatting.data_formatter import DataFormatterImpl
from app.adapters.external.formatting.database_presenter import DatabasePresenterImpl
from app.adapters.external.formatting.message_validator import MessageValidatorImpl
from app.adapters.external.formatting.notification_formatter import NotificationFormatterImpl
from app.adapters.external.formatting.response_sender import ResponseSenderImpl
from app.adapters.external.formatting.summary_presenter import SummaryPresenterImpl
from app.adapters.external.formatting.text_processor import TextProcessorImpl

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from app.core.verbosity import VerbosityResolver
    from app.services.topic_search import TopicArticle

logger = logging.getLogger(__name__)


class ResponseFormatter:
    """Handles message formatting and replies to Telegram users.

    This class is a facade that delegates to specialized components for different
    concerns while maintaining backward compatibility with existing code.
    """

    def __init__(
        self,
        safe_reply_func: Callable[[Any, str], Awaitable[None]] | None = None,
        reply_json_func: Callable[[Any, dict], Awaitable[None]] | None = None,
        telegram_client: Any = None,
        telegram_limits: Any = None,
        verbosity_resolver: VerbosityResolver | None = None,
        admin_log_chat_id: int | None = None,
    ) -> None:
        """Initialize the ResponseFormatter facade.

        Args:
            safe_reply_func: Optional callback for test compatibility.
            reply_json_func: Optional callback for test compatibility.
            telegram_client: Optional Telegram client for message operations.
            telegram_limits: Optional limits configuration object.
            verbosity_resolver: Optional resolver for per-user verbosity.
                When *None*, all notification methods behave as DEBUG (legacy).
            admin_log_chat_id: Optional chat ID for admin-level debug logging.
        """
        # Store original references for backward compatibility
        self._safe_reply_func = safe_reply_func
        self._reply_json_func = reply_json_func
        self._telegram_client = telegram_client
        self._verbosity_resolver = verbosity_resolver

        # Load limits from config (with backward-compatible defaults)
        if telegram_limits is not None:
            self.MAX_MESSAGE_CHARS = telegram_limits.max_message_chars
            self.MAX_URL_LENGTH = telegram_limits.max_url_length
            self.MAX_BATCH_URLS = telegram_limits.max_batch_urls
            self.MIN_MESSAGE_INTERVAL_MS = telegram_limits.min_message_interval_ms
        else:
            # Fallback defaults for backward compatibility
            self.MAX_MESSAGE_CHARS = 3500
            self.MAX_URL_LENGTH = 2048
            self.MAX_BATCH_URLS = 200
            self.MIN_MESSAGE_INTERVAL_MS = 100

        # Initialize components
        self._data_formatter = DataFormatterImpl()

        self._message_validator = MessageValidatorImpl(
            min_message_interval_ms=self.MIN_MESSAGE_INTERVAL_MS
        )

        self._response_sender = ResponseSenderImpl(
            self._message_validator,
            max_message_chars=self.MAX_MESSAGE_CHARS,
            safe_reply_func=safe_reply_func,
            reply_json_func=reply_json_func,
            telegram_client=telegram_client,
            admin_log_chat_id=admin_log_chat_id,
        )

        self._text_processor = TextProcessorImpl(
            self._response_sender,
            max_message_chars=self.MAX_MESSAGE_CHARS,
        )

        # Create progress tracker for Reader mode
        from app.core.progress_tracker import ProgressTracker

        self._progress_tracker = ProgressTracker(self._response_sender)

        self._notification_formatter = NotificationFormatterImpl(
            self._response_sender,
            self._data_formatter,
            safe_reply_func=safe_reply_func,
            verbosity_resolver=verbosity_resolver,
            progress_tracker=self._progress_tracker,
        )

        self._summary_presenter = SummaryPresenterImpl(
            self._response_sender,
            self._text_processor,
            self._data_formatter,
            verbosity_resolver=verbosity_resolver,
            progress_tracker=self._progress_tracker,
        )

        self._database_presenter = DatabasePresenterImpl(
            self._response_sender,
            self._data_formatter,
        )

        # Expose internal state for backward compatibility with existing code
        self._last_message_time: float = 0.0
        self._notified_error_ids: set[str] = set()

    async def is_reader_mode(self, message: Any) -> bool:
        """Return True when the user prefers Reader (consolidated) UX."""
        if self._verbosity_resolver is None:
            return False
        try:
            from app.core.verbosity import VerbosityLevel

            return (await self._verbosity_resolver.get_verbosity(message)) == VerbosityLevel.READER
        except Exception:
            logger.debug("verbosity_level_import_failed", exc_info=True)
            return False

    def __setattr__(self, name: str, value: Any) -> None:
        """Intercept attribute assignments to propagate telegram_client to components."""
        super().__setattr__(name, value)
        # Propagate telegram_client changes to response sender for backward compatibility
        # with tests that set _telegram_client after initialization
        if name == "_telegram_client" and hasattr(self, "_response_sender"):
            self._response_sender._telegram_client = value

    # =========================================================================
    # ResponseSender delegation (core Telegram sending)
    # =========================================================================

    async def safe_reply(
        self, message: Any, text: str, *, parse_mode: str | None = None, reply_markup: Any = None
    ) -> None:
        """Safely reply to a message with comprehensive security checks."""
        await self._response_sender.safe_reply(
            message, text, parse_mode=parse_mode, reply_markup=reply_markup
        )

    async def safe_reply_with_id(
        self, message: Any, text: str, *, parse_mode: str | None = None
    ) -> int | None:
        """Safely reply to a message and return the message ID."""
        return await self._response_sender.safe_reply_with_id(message, text, parse_mode=parse_mode)

    async def edit_message(
        self, chat_id: int, message_id: int, text: str, *, parse_mode: str | None = None
    ) -> bool:
        """Edit an existing message in Telegram with security checks."""
        return await self._response_sender.edit_message(
            chat_id, message_id, text, parse_mode=parse_mode
        )

    async def send_chat_action(
        self,
        chat_id: int,
        action: str = "typing",
    ) -> bool:
        """Send a chat action (typing indicator) to Telegram.

        Args:
            chat_id: The chat ID to send the action to
            action: The action type (typing, upload_photo, upload_video, upload_document, etc.)

        Returns:
            True if the action was sent successfully, False otherwise
        """
        return await self._response_sender.send_chat_action(chat_id, action)

    async def reply_json(
        self, message: Any, obj: dict, *, correlation_id: str | None = None, success: bool = True
    ) -> None:
        """Reply with JSON object, using file upload for large content."""
        await self._response_sender.reply_json(
            message, obj, correlation_id=correlation_id, success=success
        )

    def create_inline_keyboard(self, buttons: list[dict[str, str]]) -> Any:
        """Create an inline keyboard markup from button definitions."""
        return self._response_sender.create_inline_keyboard(buttons)

    # =========================================================================
    # NotificationFormatter delegation (status notifications)
    # =========================================================================

    async def send_help(self, message: Any) -> None:
        """Send help message to user."""
        await self._notification_formatter.send_help(message)

    async def send_welcome(self, message: Any) -> None:
        """Send welcome message to user."""
        await self._notification_formatter.send_welcome(message)

    async def send_url_accepted_notification(
        self, message: Any, norm: str, correlation_id: str, *, silent: bool = False
    ) -> None:
        """Send URL accepted notification."""
        await self._notification_formatter.send_url_accepted_notification(
            message, norm, correlation_id, silent=silent
        )

    async def send_firecrawl_start_notification(
        self, message: Any, url: str | None = None, *, silent: bool = False
    ) -> None:
        """Send Firecrawl start notification."""
        await self._notification_formatter.send_firecrawl_start_notification(
            message, url, silent=silent
        )

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
        await self._notification_formatter.send_firecrawl_success_notification(
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
        """Send content reuse notification with cached crawl metadata."""
        await self._notification_formatter.send_content_reuse_notification(
            message,
            http_status=http_status,
            crawl_status=crawl_status,
            latency_sec=latency_sec,
            correlation_id=correlation_id,
            options=options,
            silent=silent,
        )

    async def send_cached_summary_notification(self, message: Any, *, silent: bool = False) -> None:
        """Inform the user that a cached summary is being reused."""
        await self._notification_formatter.send_cached_summary_notification(message, silent=silent)

    async def send_html_fallback_notification(
        self, message: Any, content_len: int, *, silent: bool = False
    ) -> None:
        """Send HTML fallback notification."""
        await self._notification_formatter.send_html_fallback_notification(
            message, content_len, silent=silent
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
        """Send language detection notification."""
        await self._notification_formatter.send_language_detection_notification(
            message, detected, content_preview, url=url, silent=silent
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
        """Send content analysis notification."""
        await self._notification_formatter.send_content_analysis_notification(
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
        """Send LLM start notification."""
        await self._notification_formatter.send_llm_start_notification(
            message, model, content_len, structured_output_mode, url=url, silent=silent
        )

    async def send_llm_completion_notification(
        self, message: Any, llm: Any, correlation_id: str, *, silent: bool = False
    ) -> None:
        """Send LLM completion notification."""
        await self._notification_formatter.send_llm_completion_notification(
            message, llm, correlation_id, silent=silent
        )

    async def send_forward_accepted_notification(self, message: Any, title: str) -> None:
        """Send forward request accepted notification."""
        await self._notification_formatter.send_forward_accepted_notification(message, title)

    async def send_forward_language_notification(self, message: Any, detected: str | None) -> None:
        """Send forward language detection notification."""
        await self._notification_formatter.send_forward_language_notification(message, detected)

    async def send_forward_completion_notification(self, message: Any, llm: Any) -> None:
        """Send forward completion notification."""
        await self._notification_formatter.send_forward_completion_notification(message, llm)

    async def send_youtube_download_notification(
        self, message: Any, url: str, *, silent: bool = False
    ) -> None:
        """Notify user that YouTube video download is starting."""
        await self._notification_formatter.send_youtube_download_notification(
            message, url, silent=silent
        )

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
        await self._notification_formatter.send_youtube_download_complete_notification(
            message, title, resolution, size_mb, silent=silent
        )

    async def send_error_notification(
        self,
        message: Any,
        error_type: str,
        correlation_id: str,
        details: str | None = None,
    ) -> None:
        """Send error notification with rich formatting."""
        await self._notification_formatter.send_error_notification(
            message, error_type, correlation_id, details
        )

    # =========================================================================
    # SummaryPresenter delegation (summary presentation)
    # =========================================================================

    async def send_structured_summary_response(
        self,
        message: Any,
        summary_shaped: dict[str, Any],
        llm: Any,
        chunks: int | None = None,
        summary_id: int | str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Send summary where each top-level JSON field is a separate message."""
        await self._summary_presenter.send_structured_summary_response(
            message,
            summary_shaped,
            llm,
            chunks,
            summary_id=summary_id,
            correlation_id=correlation_id,
        )

    async def send_forward_summary_response(
        self, message: Any, forward_shaped: dict[str, Any], summary_id: int | str | None = None
    ) -> None:
        """Send forward summary with per-field messages."""
        await self._summary_presenter.send_forward_summary_response(
            message, forward_shaped, summary_id=summary_id
        )

    async def send_russian_translation(
        self, message: Any, translated_text: str, correlation_id: str | None = None
    ) -> None:
        """Send the adapted Russian translation as a follow-up message."""
        await self._summary_presenter.send_russian_translation(
            message, translated_text, correlation_id
        )

    async def send_additional_insights_message(
        self, message: Any, insights: dict[str, Any], correlation_id: str | None = None
    ) -> None:
        """Send follow-up message summarizing additional research insights."""
        await self._summary_presenter.send_additional_insights_message(
            message, insights, correlation_id
        )

    async def send_custom_article(self, message: Any, article: dict[str, Any]) -> None:
        """Send the custom generated article with a nice header and downloadable JSON."""
        await self._summary_presenter.send_custom_article(message, article)

    # =========================================================================
    # DatabasePresenter delegation (database UI)
    # =========================================================================

    async def send_db_overview(self, message: Any, overview: dict[str, object]) -> None:
        """Send an overview of the database state."""
        await self._database_presenter.send_db_overview(message, overview)

    async def send_topic_search_results(
        self,
        message: Any,
        *,
        topic: str,
        articles: Sequence[TopicArticle],
        source: str = "online",
    ) -> None:
        """Send a formatted list of topic search results to the user."""
        await self._database_presenter.send_topic_search_results(
            message, topic=topic, articles=articles, source=source
        )

    async def send_db_verification(self, message: Any, verification: dict[str, Any]) -> None:
        """Send database verification summary highlighting missing fields."""
        await self._database_presenter.send_db_verification(message, verification)

    async def send_db_reprocess_start(
        self,
        message: Any,
        *,
        url_targets: list[dict[str, Any]],
        skipped: list[dict[str, Any]],
    ) -> None:
        """Notify the user that reprocessing of missing posts has started."""
        await self._database_presenter.send_db_reprocess_start(
            message, url_targets=url_targets, skipped=skipped
        )

    async def send_db_reprocess_complete(
        self,
        message: Any,
        *,
        url_targets: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        skipped: list[dict[str, Any]],
    ) -> None:
        """Summarize the outcome of the automated reprocessing."""
        await self._database_presenter.send_db_reprocess_complete(
            message, url_targets=url_targets, failures=failures, skipped=skipped
        )

    # =========================================================================
    # Private methods exposed for backward compatibility with tests
    # =========================================================================

    def _is_safe_content(self, text: str) -> tuple[bool, str]:
        """Validate content for security issues."""
        return self._message_validator.is_safe_content(text)

    def _validate_url(self, url: str) -> tuple[bool, str]:
        """Validate URL for security."""
        return self._message_validator.validate_url(url)

    async def _check_rate_limit(self) -> bool:
        """Ensure replies respect the minimum delay between Telegram messages."""
        return await self._message_validator.check_rate_limit()

    def _chunk_text(self, text: str, *, max_len: int) -> list[str]:
        """Split text into chunks respecting Telegram's message length limit."""
        return self._text_processor.chunk_text(text, max_len=max_len)

    def _find_split_index(self, text: str, limit: int) -> int:
        """Find a sensible split index before the limit."""
        return self._text_processor._find_split_index(text, limit)

    def _sanitize_summary_text(self, text: str) -> str:
        """Normalize and clean summary text for safe sending."""
        return self._text_processor.sanitize_summary_text(text)

    def _slugify(self, text: str, *, max_len: int = 60) -> str:
        """Create a filesystem-friendly slug from text."""
        return self._text_processor.slugify(text, max_len=max_len)

    def _build_json_filename(self, obj: dict) -> str:
        """Build a descriptive filename for the JSON attachment."""
        return self._text_processor.build_json_filename(obj)

    async def _send_long_text(self, message: Any, text: str) -> None:
        """Send text, splitting into multiple messages if too long for Telegram."""
        await self._text_processor.send_long_text(message, text)

    async def _send_labelled_text(self, message: Any, label: str, body: str) -> None:
        """Send labelled text, splitting into continuation messages when needed."""
        await self._text_processor.send_labelled_text(message, label, body)

    def _format_bytes(self, size: int) -> str:
        """Convert byte count into a human-readable string."""
        return self._data_formatter.format_bytes(size)

    def _format_metric_value(self, value: Any) -> str | None:
        """Format metric values, trimming insignificant decimals and booleans."""
        return self._data_formatter.format_metric_value(value)

    def _format_key_stats(self, key_stats: list[dict[str, Any]]) -> list[str]:
        """Render key statistics into bullet-point lines."""
        return self._data_formatter.format_key_stats(key_stats)

    def _format_readability(self, readability: Any) -> str | None:
        """Create a reader-friendly readability summary line."""
        return self._data_formatter.format_readability(readability)

    def _format_firecrawl_options(self, options: dict[str, Any] | None) -> str | None:
        """Format Firecrawl options into a display string."""
        return self._data_formatter.format_firecrawl_options(options)

    async def _send_new_field_messages(self, message: Any, shaped: dict[str, Any]) -> None:
        """Send messages for new fields like extractive quotes, highlights, etc."""
        await self._summary_presenter._send_new_field_messages(message, shaped)
