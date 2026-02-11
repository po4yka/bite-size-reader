"""URL handling for Telegram bot messages."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from app.adapters.telegram.message_router_helpers import process_url_batch
from app.core.url_utils import extract_all_urls
from app.core.verbosity import VerbosityLevel
from app.db.user_interactions import async_safe_update_user_interaction
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
)

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.core.verbosity import VerbosityResolver
    from app.db.session import DatabaseSessionManager
    from app.services.adaptive_timeout import AdaptiveTimeoutService

logger = logging.getLogger(__name__)


# URL processing configuration (defaults when adaptive timeout is disabled)
URL_MAX_CONCURRENT = 4
URL_MAX_RETRIES = 2  # was 3: fewer retries, each with more time
URL_INITIAL_TIMEOUT_SEC = 900.0  # 15 min: allows for slow LLM response generation
URL_MAX_TIMEOUT_SEC = 1800.0  # 30 min: cap for retries with backoff
URL_BACKOFF_BASE = 3.0  # was 2.0: longer backoff between retries
URL_BACKOFF_MAX = 60.0

# Domain fail-fast configuration: require multiple failures before skipping siblings
# This prevents one slow URL from immediately killing all sibling URLs
DOMAIN_FAILFAST_THRESHOLD = 2  # Require 2+ failures before skipping domain siblings


def _extract_domain(url: str | None) -> str | None:
    """Extract domain from URL, normalizing www prefix."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower() if domain else None
    except Exception:
        return None


class URLHandler:
    """Handles URL-related message processing and state management."""

    def __init__(
        self,
        db: DatabaseSessionManager,
        response_formatter: ResponseFormatter,
        url_processor: URLProcessor,
        adaptive_timeout_service: AdaptiveTimeoutService | None = None,
        verbosity_resolver: VerbosityResolver | None = None,
        # Optional: combined summary feature dependencies
        llm_client: Any | None = None,
        batch_session_repo: Any | None = None,
        batch_config: Any | None = None,
    ) -> None:
        self.db = db
        self.user_repo = SqliteUserRepositoryAdapter(db)
        self.request_repo = SqliteRequestRepositoryAdapter(db)
        self.response_formatter = response_formatter
        self.url_processor = url_processor
        self._adaptive_timeout = adaptive_timeout_service
        self.verbosity_resolver = verbosity_resolver
        # Combined summary dependencies
        self._llm_client = llm_client
        self._batch_session_repo = batch_session_repo
        self._batch_config = batch_config

        # Lock to protect shared state from concurrent access
        self._state_lock = asyncio.Lock()
        # In-memory state with timestamps for TTL expiry
        self._state_ttl_sec = 120  # 2 minutes
        # uid -> timestamp when added
        self._awaiting_url_users: dict[int, float] = {}

    async def _compute_url_timeout(self, url: str, attempt: int = 0) -> float:
        """Compute timeout for URL processing, using adaptive timeout if available.

        Args:
            url: The URL being processed
            attempt: Current retry attempt (0-indexed)

        Returns:
            Timeout in seconds, applying exponential backoff for retries
        """
        # Get base timeout from adaptive service or use static default
        if self._adaptive_timeout and self._adaptive_timeout.enabled:
            try:
                domain = _extract_domain(url)
                estimate = await self._adaptive_timeout.get_timeout(url=url, domain=domain)
                base_timeout = estimate.timeout_sec

                logger.debug(
                    "adaptive_timeout_selected",
                    extra={
                        "url": url,
                        "domain": domain,
                        "base_timeout_sec": base_timeout,
                        "source": estimate.source,
                        "confidence": estimate.confidence,
                        "attempt": attempt,
                    },
                )
            except Exception as e:
                logger.warning(
                    "adaptive_timeout_error_using_default",
                    extra={"url": url, "error": str(e)},
                )
                base_timeout = URL_INITIAL_TIMEOUT_SEC
        else:
            base_timeout = URL_INITIAL_TIMEOUT_SEC

        # Apply exponential backoff for retries (1.5x per attempt)
        current_timeout = base_timeout * (1.5**attempt)

        # Clamp to max timeout
        return min(current_timeout, URL_MAX_TIMEOUT_SEC)

    async def _apply_url_security_checks(
        self, message: Any, urls: list[str], uid: int, correlation_id: str
    ) -> list[str]:
        """Apply shared security checks for URLs from Telegram messages."""
        if not urls:
            return []

        # Security check: limit batch size
        if len(urls) > self.response_formatter.MAX_BATCH_URLS:
            await self.response_formatter.safe_reply(
                message,
                f"❌ Too many URLs ({len(urls)}). "
                f"Maximum allowed: {self.response_formatter.MAX_BATCH_URLS}.",
            )
            logger.warning(
                "url_batch_limit_exceeded",
                extra={
                    "url_count": len(urls),
                    "max_allowed": self.response_formatter.MAX_BATCH_URLS,
                    "uid": uid,
                },
            )
            return []

        valid_urls = []
        for url in urls:
            is_valid, error_msg = self.response_formatter._validate_url(url)
            if is_valid:
                valid_urls.append(url)
            else:
                logger.warning(
                    "invalid_url_submitted",
                    extra={"url": url, "error": error_msg, "uid": uid, "cid": correlation_id},
                )

        if not valid_urls:
            await self.response_formatter.send_error_notification(
                message,
                "no_urls_found",
                correlation_id,
                details="All submitted URLs failed security or validation checks.",
            )
        return valid_urls

    async def _process_multiple_urls_parallel(
        self,
        message: Any,
        urls: list[str],
        uid: int,
        correlation_id: str,
        initial_message_id: int | None = None,
    ) -> None:
        """Process multiple URLs in parallel with controlled concurrency and detailed status tracking."""
        # Adaptive concurrency: 2-4 concurrent based on batch size
        max_concurrent = max(2, min(URL_MAX_CONCURRENT, len(urls)))

        # Define timeout function using adaptive service
        async def compute_timeout(url: str, attempt: int) -> float:
            return await self._compute_url_timeout(url, attempt)

        # Use unified batch processor from message_router_helpers
        await process_url_batch(
            message=message,
            urls=urls,
            uid=uid,
            correlation_id=correlation_id,
            url_processor=self.url_processor,
            response_formatter=self.response_formatter,
            request_repo=self.request_repo,
            user_repo=self.user_repo,
            max_concurrent=max_concurrent,
            max_retries=URL_MAX_RETRIES,
            compute_timeout_func=compute_timeout,
            initial_message_id=initial_message_id,
            # Combined summary dependencies (optional)
            llm_client=self._llm_client,
            batch_session_repo=self._batch_session_repo,
            batch_config=self._batch_config,
        )

    async def add_awaiting_user(self, uid: int) -> None:
        """Add user to awaiting URL list."""
        async with self._state_lock:
            self._awaiting_url_users[uid] = time.time()

    async def cancel_pending_requests(self, uid: int) -> tuple[bool, bool]:
        """Cancel any pending URL requests for a user.

        Returns (awaiting_cancelled, False) for backward compatibility.
        """
        async with self._state_lock:
            awaiting_cancelled = uid in self._awaiting_url_users
            if awaiting_cancelled:
                self._awaiting_url_users.pop(uid, None)

            return awaiting_cancelled, False

    async def handle_awaited_url(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle URL sent after /summarize command."""
        urls = extract_all_urls(text)
        async with self._state_lock:
            self._awaiting_url_users.pop(uid, None)

        urls = await self._apply_url_security_checks(message, urls, uid, correlation_id)
        if not urls:
            return

        if len(urls) > 1:
            progress_message_id = await self.response_formatter.safe_reply_with_id(
                message, f"🚀 Preparing to process {len(urls)} links..."
            )
            await self._process_multiple_urls_parallel(
                message, urls, uid, correlation_id, initial_message_id=progress_message_id
            )
            return

        if len(urls) == 1:
            logger.debug("received_awaited_url", extra={"uid": uid, "cid": correlation_id})

            # Determine if Reader mode (progress tracker) or Debug mode (typing indicators)
            progress_tracker = None
            if self.verbosity_resolver:
                verbosity = await self.verbosity_resolver.get_verbosity(message)
                if verbosity == VerbosityLevel.READER:
                    # Use existing progress tracker for editable progress messages
                    progress_tracker = self.response_formatter.progress_tracker

            await self.url_processor.handle_url_flow(
                message,
                urls[0],
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                progress_tracker=progress_tracker,
            )

    async def handle_direct_url(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle direct URL message with security validation."""
        urls = extract_all_urls(text)
        urls = await self._apply_url_security_checks(message, urls, uid, correlation_id)
        if not urls:
            return

        if len(urls) > 1:
            # Process multiple URLs directly in parallel (no confirmation needed)
            progress_message_id = await self.response_formatter.safe_reply_with_id(
                message, f"Processing {len(urls)} links in parallel..."
            )
            await self._process_multiple_urls_parallel(
                message, urls, uid, correlation_id, initial_message_id=progress_message_id
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.user_repo,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="processing",
                    start_time=start_time,
                    logger_=logger,
                )
            return

        if len(urls) == 1:
            # Determine if Reader mode (progress tracker) or Debug mode (typing indicators)
            progress_tracker = None
            if self.verbosity_resolver:
                verbosity = await self.verbosity_resolver.get_verbosity(message)
                if verbosity == VerbosityLevel.READER:
                    # Use existing progress tracker for editable progress messages
                    progress_tracker = self.response_formatter.progress_tracker

            await self.url_processor.handle_url_flow(
                message,
                urls[0],
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                progress_tracker=progress_tracker,
            )

    async def is_awaiting_url(self, uid: int) -> bool:
        """Check if user is awaiting a URL (respects TTL)."""
        async with self._state_lock:
            ts = self._awaiting_url_users.get(uid)
            if ts is None:
                return False
            if time.time() - ts > self._state_ttl_sec:
                self._awaiting_url_users.pop(uid, None)
                return False
            return True

    async def cleanup_expired_state(self) -> int:
        """Remove expired awaiting entries. Returns count removed."""
        async with self._state_lock:
            now = time.time()
            cleaned = 0
            expired_awaiting = [
                uid
                for uid, ts in self._awaiting_url_users.items()
                if now - ts > self._state_ttl_sec
            ]
            for uid in expired_awaiting:
                del self._awaiting_url_users[uid]
                cleaned += 1
            return cleaned
