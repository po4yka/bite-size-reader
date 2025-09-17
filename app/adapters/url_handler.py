"""URL handling for Telegram bot messages."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import extract_all_urls

if TYPE_CHECKING:
    from app.adapters.response_formatter import ResponseFormatter
    from app.adapters.url_processor import URLProcessor

logger = logging.getLogger(__name__)


class URLHandler:
    """Handles URL-related message processing and state management."""

    def __init__(
        self,
        response_formatter: ResponseFormatter,
        url_processor: URLProcessor,
    ) -> None:
        self.response_formatter = response_formatter
        self.url_processor = url_processor

        # Simple in-memory state: users awaiting a URL after /summarize
        self._awaiting_url_users: set[int] = set()
        # Pending multiple links confirmation: uid -> list of urls
        self._pending_multi_links: dict[int, list[str]] = {}

    def add_awaiting_user(self, uid: int) -> None:
        """Add user to awaiting URL list."""
        self._awaiting_url_users.add(uid)

    def add_pending_multi_links(self, uid: int, urls: list[str]) -> None:
        """Add user to pending multi-links confirmation."""
        self._pending_multi_links[uid] = urls

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
        self._awaiting_url_users.discard(uid)

        if len(urls) > 1:
            self._pending_multi_links[uid] = urls
            await self.response_formatter.safe_reply(
                message, f"Process {len(urls)} links? (yes/no)"
            )
            logger.debug("awaiting_multi_confirm", extra={
                         "uid": uid, "count": len(urls)})
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="confirmation",
                    processing_time_ms=int((time.time() - start_time) * 1000),
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
        """Handle direct URL message."""
        urls = extract_all_urls(text)

        if len(urls) > 1:
            self._pending_multi_links[uid] = urls
            await self.response_formatter.safe_reply(
                message, f"Process {len(urls)} links? (yes/no)"
            )
            logger.debug("awaiting_multi_confirm", extra={
                         "uid": uid, "count": len(urls)})
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="confirmation",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
        elif len(urls) == 1:
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
        """Handle yes/no confirmation for multiple links."""
        if self._is_affirmative(text):
            urls = self._pending_multi_links.pop(uid)
            await self.response_formatter.safe_reply(message, f"Processing {len(urls)} links...")
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="processing",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
            for u in urls:
                per_link_cid = generate_correlation_id()
                logger.debug(
                    "processing_link",
                    extra={"uid": uid, "url": u, "cid": per_link_cid},
                )
                await self.url_processor.handle_url_flow(message, u, correlation_id=per_link_cid)
            return

        if self._is_negative(text):
            self._pending_multi_links.pop(uid, None)
            await self.response_formatter.safe_reply(message, "Cancelled.")
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="cancelled",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

    def is_awaiting_url(self, uid: int) -> bool:
        """Check if user is awaiting a URL."""
        return uid in self._awaiting_url_users

    def has_pending_multi_links(self, uid: int) -> bool:
        """Check if user has pending multi-link confirmation."""
        return uid in self._pending_multi_links

    def _is_affirmative(self, text: str) -> bool:
        """Check if text is an affirmative response."""
        t = text.strip().lower()
        return t in {"y", "yes", "+", "ok", "okay", "sure", "да", "ага", "угу", "👍", "✅"}

    def _is_negative(self, text: str) -> bool:
        """Check if text is a negative response."""
        t = text.strip().lower()
        return t in {"n", "no", "-", "cancel", "stop", "нет", "не"}

    def _update_user_interaction(
        self,
        *,
        interaction_id: int,
        response_sent: bool | None = None,
        response_type: str | None = None,
        error_occurred: bool | None = None,
        error_message: str | None = None,
        processing_time_ms: int | None = None,
        request_id: int | None = None,
    ) -> None:
        """Update an existing user interaction record."""
        # Note: This method is a placeholder for future user interaction tracking
        # The current database schema doesn't include user_interactions table
        logger.debug(
            "user_interaction_update_placeholder",
            extra={"interaction_id": interaction_id,
                   "response_type": response_type},
        )
