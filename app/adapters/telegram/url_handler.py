"""URL handling for Telegram bot messages."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.adapters.repository_ports import (
    RequestRepositoryPort,
    UserRepositoryPort,
    create_request_repository,
    create_user_repository,
)
from app.adapters.telegram.url_batch_policy_service import URLBatchPolicyService
from app.adapters.telegram.url_state_store import URLAwaitingStateStore
from app.core.url_utils import extract_all_urls
from app.core.verbosity import VerbosityLevel
from app.db.user_interactions import async_safe_update_user_interaction

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.core.verbosity import VerbosityResolver
    from app.db.session import DatabaseSessionManager
    from app.services.adaptive_timeout import AdaptiveTimeoutService

logger = logging.getLogger(__name__)


class URLHandler:
    """Handles URL-related message processing and state management."""

    def __init__(
        self,
        db: DatabaseSessionManager,
        response_formatter: ResponseFormatter,
        url_processor: URLProcessor,
        adaptive_timeout_service: AdaptiveTimeoutService | None = None,
        verbosity_resolver: VerbosityResolver | None = None,
        llm_client: Any | None = None,
        batch_session_repo: Any | None = None,
        batch_config: Any | None = None,
        user_repo: UserRepositoryPort | None = None,
        request_repo: RequestRepositoryPort | None = None,
        batch_policy: URLBatchPolicyService | None = None,
        awaiting_state: URLAwaitingStateStore | None = None,
    ) -> None:
        self.db = db
        self.user_repo = user_repo or create_user_repository(db)
        self.request_repo = request_repo or create_request_repository(db)
        self.response_formatter = response_formatter
        self.url_processor = url_processor
        self._adaptive_timeout = adaptive_timeout_service
        self.verbosity_resolver = verbosity_resolver

        self._llm_client = llm_client
        self._batch_session_repo = batch_session_repo
        self._batch_config = batch_config

        self._batch_policy = batch_policy or URLBatchPolicyService()
        self._awaiting_state = awaiting_state or URLAwaitingStateStore(ttl_sec=120)

        # Backward-compatible attribute for tests/introspection.
        self._awaiting_url_users = self._awaiting_state.raw_state

    async def _compute_url_timeout(self, url: str, attempt: int = 0) -> float:
        """Compatibility wrapper around URL batch timeout policy."""
        return await self._batch_policy.compute_timeout(
            url=url,
            attempt=attempt,
            adaptive_timeout_service=self._adaptive_timeout,
        )

    async def _apply_url_security_checks(
        self, message: Any, urls: list[str], uid: int, correlation_id: str
    ) -> list[str]:
        """Compatibility wrapper around URL security policy."""
        return await self._batch_policy.apply_security_checks(
            message=message,
            urls=urls,
            uid=uid,
            correlation_id=correlation_id,
            response_formatter=self.response_formatter,
        )

    async def _process_multiple_urls_parallel(
        self,
        message: Any,
        urls: list[str],
        uid: int,
        correlation_id: str,
        initial_message_id: int | None = None,
    ) -> None:
        """Compatibility wrapper around URL batch execution policy."""
        await self._batch_policy.process_multiple_urls_parallel(
            message=message,
            urls=urls,
            uid=uid,
            correlation_id=correlation_id,
            url_processor=self.url_processor,
            response_formatter=self.response_formatter,
            request_repo=self.request_repo,
            user_repo=self.user_repo,
            adaptive_timeout_service=self._adaptive_timeout,
            llm_client=self._llm_client,
            batch_session_repo=self._batch_session_repo,
            batch_config=self._batch_config,
            initial_message_id=initial_message_id,
        )

    async def add_awaiting_user(self, uid: int) -> None:
        """Add user to awaiting URL list."""
        await self._awaiting_state.add(uid)

    async def cancel_pending_requests(self, uid: int) -> tuple[bool, bool]:
        """Cancel any pending URL requests for a user.

        Returns (awaiting_cancelled, False) for backward compatibility.
        """
        awaiting_cancelled = await self._awaiting_state.remove(uid)
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
        _ = start_time
        urls = extract_all_urls(text)
        await self._awaiting_state.consume(uid)

        urls = await self._apply_url_security_checks(message, urls, uid, correlation_id)
        if not urls:
            return

        if len(urls) > 1:
            progress_message_id = await self._create_batch_progress_message(
                message=message,
                urls_count=len(urls),
                text_template="🚀 Preparing to process {count} links...",
            )
            await self._process_multiple_urls_parallel(
                message,
                urls,
                uid,
                correlation_id,
                initial_message_id=progress_message_id,
            )
            return

        await self._process_single_url(
            message=message,
            url=urls[0],
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
            progress_message_id = await self._create_batch_progress_message(
                message=message,
                urls_count=len(urls),
                text_template="Processing {count} links in parallel...",
            )
            await self._process_multiple_urls_parallel(
                message,
                urls,
                uid,
                correlation_id,
                initial_message_id=progress_message_id,
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

        await self._process_single_url(
            message=message,
            url=urls[0],
            correlation_id=correlation_id,
            interaction_id=interaction_id,
        )

    async def is_awaiting_url(self, uid: int) -> bool:
        """Check if user is awaiting a URL (respects TTL)."""
        return await self._awaiting_state.contains(uid)

    async def cleanup_expired_state(self) -> int:
        """Remove expired awaiting entries. Returns count removed."""
        return await self._awaiting_state.cleanup_expired()

    async def _process_single_url(
        self,
        *,
        message: Any,
        url: str,
        correlation_id: str,
        interaction_id: int,
    ) -> None:
        progress_tracker = await self._resolve_progress_tracker(message)
        await self.url_processor.handle_url_flow(
            message,
            url,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            progress_tracker=progress_tracker,
        )

    async def _resolve_progress_tracker(self, message: Any) -> Any | None:
        if not self.verbosity_resolver:
            return None

        verbosity = await self.verbosity_resolver.get_verbosity(message)
        if verbosity != VerbosityLevel.READER:
            return None

        return self.response_formatter.progress_tracker

    async def _create_batch_progress_message(
        self,
        *,
        message: Any,
        urls_count: int,
        text_template: str,
    ) -> int | None:
        if self._is_draft_streaming_enabled():
            return None

        return await self.response_formatter.safe_reply_with_id(
            message,
            text_template.format(count=urls_count),
        )

    def _is_draft_streaming_enabled(self) -> bool:
        checker = getattr(self.response_formatter.sender, "is_draft_streaming_enabled", None)
        if not callable(checker):
            return False

        try:
            enabled = checker()
        except Exception:
            return False

        return enabled if isinstance(enabled, bool) else False
