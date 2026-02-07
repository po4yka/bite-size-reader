"""URL handling for Telegram bot messages."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from app.adapters.telegram.message_router_helpers import process_url_batch
from app.core.url_utils import extract_all_urls
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
    ) -> None:
        self.db = db
        self.user_repo = SqliteUserRepositoryAdapter(db)
        self.request_repo = SqliteRequestRepositoryAdapter(db)
        self.response_formatter = response_formatter
        self.url_processor = url_processor
        self._adaptive_timeout = adaptive_timeout_service

        # Lock to protect shared state from concurrent access
        self._state_lock = asyncio.Lock()
        # In-memory state with timestamps for TTL expiry
        self._state_ttl_sec = 120  # 2 minutes
        # uid -> timestamp when added
        self._awaiting_url_users: dict[int, float] = {}
        self._pending_multi_links: dict[int, tuple[list[str], float]] = {}

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
                    "invalid_url_submitted", extra={"url": url, "error": error_msg, "uid": uid}
                )

        if not valid_urls:
            await self.response_formatter.send_error_notification(
                message,
                "no_urls_found",
                correlation_id,
                details="All submitted URLs failed security or validation checks.",
            )
        return valid_urls

    async def _request_multi_link_confirmation(
        self,
        message: Any,
        uid: int,
        urls: list[str],
        interaction_id: int,
        start_time: float,
    ) -> None:
        async with self._state_lock:
            self._pending_multi_links[uid] = (urls, time.time())
        # Create inline keyboard buttons for confirmation
        buttons = [
            {"text": "✅ Yes", "callback_data": "multi_confirm_yes"},
            {"text": "❌ No", "callback_data": "multi_confirm_no"},
        ]
        keyboard = self.response_formatter.create_inline_keyboard(buttons)
        await self.response_formatter.safe_reply(
            message, f"Process {len(urls)} links?", reply_markup=keyboard
        )
        logger.debug("awaiting_multi_confirm", extra={"uid": uid, "count": len(urls)})
        if interaction_id:
            await async_safe_update_user_interaction(
                self.user_repo,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="confirmation",
                start_time=start_time,
                logger_=logger,
            )

    async def _process_multiple_urls_parallel(
        self,
        message: Any,
        urls: list[str],
        uid: int,
        correlation_id: str,
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
        )

    async def add_awaiting_user(self, uid: int) -> None:
        """Add user to awaiting URL list."""
        async with self._state_lock:
            self._awaiting_url_users[uid] = time.time()

    async def add_pending_multi_links(self, uid: int, urls: list[str]) -> None:
        """Add user to pending multi-links confirmation."""
        async with self._state_lock:
            self._pending_multi_links[uid] = (urls, time.time())

    async def cancel_pending_requests(self, uid: int) -> tuple[bool, bool]:
        """Cancel any pending URL or multi-link confirmation requests for a user."""
        async with self._state_lock:
            awaiting_cancelled = uid in self._awaiting_url_users
            if awaiting_cancelled:
                self._awaiting_url_users.pop(uid, None)

            multi_cancelled = uid in self._pending_multi_links
            if multi_cancelled:
                self._pending_multi_links.pop(uid, None)

            return awaiting_cancelled, multi_cancelled

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
            await self._request_multi_link_confirmation(
                message, uid, urls, interaction_id, start_time
            )
            return

        if len(urls) == 1:
            logger.debug("received_awaited_url", extra={"uid": uid})
            await self.url_processor.handle_url_flow(
                message,
                urls[0],
                correlation_id=correlation_id,
                interaction_id=interaction_id,
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
            await self._request_multi_link_confirmation(
                message, uid, urls, interaction_id, start_time
            )
            return

        if len(urls) == 1:
            await self.url_processor.handle_url_flow(
                message,
                urls[0],
                correlation_id=correlation_id,
                interaction_id=interaction_id,
            )

    async def handle_multi_link_confirmation(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle yes/no confirmation for multiple links with optimized parallel processing."""
        normalized = self._normalize_response(text)

        if self._is_affirmative(normalized):
            # CRITICAL: Keep lock held during state validation to prevent race conditions
            async with self._state_lock:
                entry = self._pending_multi_links.get(uid)

                # Unpack timestamped entry
                urls: list[str] | None = None
                if entry is not None:
                    urls = entry[0]

                # Validate state while holding lock
                if not urls:
                    logger.warning(
                        "multi_confirm_missing_state", extra={"uid": uid, "cid": correlation_id}
                    )
                else:
                    # Validate URLs while holding lock
                    is_valid = isinstance(urls, list) and all(
                        isinstance(url, str) and url.strip() for url in urls
                    )

                    if not is_valid:
                        logger.warning(
                            "multi_confirm_invalid_state",
                            extra={
                                "uid": uid,
                                "cid": correlation_id,
                            },
                        )
                        self._pending_multi_links.pop(uid, None)
                        urls = None
                    else:
                        self._pending_multi_links.pop(uid, None)

            if not urls:
                await self.response_formatter.safe_reply(
                    message,
                    "ℹ️ No pending multi-link request to confirm. Please send the links again.",
                )
                return

            await self.response_formatter.safe_reply(
                message, f"🚀 Processing {len(urls)} links in parallel..."
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

            # Process URLs in parallel with controlled concurrency
            await self._process_multiple_urls_parallel(message, urls, uid, correlation_id)
            return

        if self._is_negative(normalized):
            async with self._state_lock:
                self._pending_multi_links.pop(uid, None)
            await self.response_formatter.safe_reply(message, "Cancelled.")
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.user_repo,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="cancelled",
                    start_time=start_time,
                    logger_=logger,
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

    async def has_pending_multi_links(self, uid: int) -> bool:
        """Check if user has pending multi-link confirmation (respects TTL)."""
        async with self._state_lock:
            entry = self._pending_multi_links.get(uid)
            if entry is None:
                return False
            if time.time() - entry[1] > self._state_ttl_sec:
                self._pending_multi_links.pop(uid, None)
                return False
            return True

    async def cleanup_expired_state(self) -> int:
        """Remove expired awaiting/pending entries. Returns count removed."""
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
            expired_multi = [
                uid
                for uid, (_, ts) in self._pending_multi_links.items()
                if now - ts > self._state_ttl_sec
            ]
            for uid in expired_multi:
                del self._pending_multi_links[uid]
                cleaned += 1
            return cleaned

    def _normalize_response(self, text: str) -> str:
        return text.strip().lower()

    def _is_affirmative(self, text: str) -> bool:
        """Check if text is an affirmative response."""
        return text in {"y", "yes", "+", "ok", "okay", "sure", "да", "ага", "угу", "👍", "✅"}

    def _is_negative(self, text: str) -> bool:
        """Check if text is a negative response."""
        return text in {"n", "no", "-", "cancel", "stop", "нет", "не"}
