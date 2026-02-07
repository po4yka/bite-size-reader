"""Command processing facade for Telegram bot.

This module provides the CommandProcessor class, which serves as a facade for
the decomposed command handler components. It maintains backward compatibility
with existing code while delegating to specialized handlers.

Handlers:
- OnboardingHandlerImpl: /start, /help
- AdminHandlerImpl: /dbinfo, /dbverify
- URLCommandsHandlerImpl: /summarize, /summarize_all, /cancel
- ContentHandlerImpl: /unread, /read
- SearchHandlerImpl: /find*, /search
- KarakeepHandlerImpl: /sync_karakeep
"""

# ruff: noqa: E501
# flake8: noqa

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.adapters.telegram.command_handlers.admin_handler import AdminHandlerImpl
from app.adapters.telegram.command_handlers.content_handler import ContentHandlerImpl
from app.adapters.telegram.command_handlers.execution_context import CommandExecutionContext
from app.adapters.telegram.command_handlers.karakeep_handler import KarakeepHandlerImpl
from app.adapters.telegram.command_handlers.onboarding_handler import OnboardingHandlerImpl
from app.adapters.telegram.command_handlers.search_handler import SearchHandlerImpl
from app.adapters.telegram.command_handlers.settings_handler import SettingsHandlerImpl
from app.adapters.telegram.command_handlers.url_commands_handler import URLCommandsHandlerImpl
from app.adapters.telegram.command_handlers.utils import maybe_load_json
from app.adapters.telegram.task_manager import UserTaskManager
from app.config import AppConfig
from app.infrastructure.persistence.sqlite.repositories.llm_repository import (
    SqliteLLMRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
)
from app.services.topic_search import LocalTopicSearchService, TopicSearchService

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.url_handler import URLHandler
    from app.db.session import DatabaseSessionManager
    from app.services.hybrid_search_service import HybridSearchService

logger = logging.getLogger(__name__)


class CommandProcessor:
    """Handles bot command processing.

    This class is a facade that delegates to specialized handler components
    while maintaining backward compatibility with existing code.

    The facade pattern is used to:
    - Preserve the existing public API
    - Allow incremental migration to the new handler architecture
    - Enable unit testing of individual handlers in isolation
    """

    def __init__(
        self,
        cfg: AppConfig,
        response_formatter: ResponseFormatter,
        db: DatabaseSessionManager,
        url_processor: URLProcessor,
        audit_func: Callable[[str, str, dict], None],
        url_handler: URLHandler | None = None,
        topic_searcher: TopicSearchService | None = None,
        local_searcher: LocalTopicSearchService | None = None,
        task_manager: UserTaskManager | None = None,
        container: Any | None = None,
        hybrid_search: HybridSearchService | None = None,
        verbosity_resolver: Any | None = None,
    ) -> None:
        """Initialize the CommandProcessor facade.

        Args:
            cfg: Application configuration.
            response_formatter: Response formatter for sending messages.
            db: Database session manager.
            url_processor: URL processor for handling URL flows.
            audit_func: Callback function for audit logging.
            url_handler: URL handler for managing pending requests.
            topic_searcher: Online topic search service.
            local_searcher: Local database topic search service.
            task_manager: Task manager for tracking active tasks.
            container: Optional DI container for hexagonal architecture.
            hybrid_search: Hybrid semantic search service.
        """
        self.cfg = cfg
        self.response_formatter = response_formatter
        self.db = db
        self._audit = audit_func

        # Initialize repositories
        self.user_repo = SqliteUserRepositoryAdapter(db)
        self.summary_repo = SqliteSummaryRepositoryAdapter(db)
        self.request_repo = SqliteRequestRepositoryAdapter(db)
        self.llm_repo = SqliteLLMRepositoryAdapter(db)

        # Store references for backward compatibility and delegation
        self.url_processor = url_processor
        self.url_handler: URLHandler | None = url_handler
        self.topic_searcher = topic_searcher
        self.local_searcher = local_searcher
        self._task_manager = task_manager
        self._container = container
        self.hybrid_search = hybrid_search

        # Initialize handler components
        self._onboarding = OnboardingHandlerImpl(response_formatter)

        self._admin = AdminHandlerImpl(
            db=db,
            response_formatter=response_formatter,
            url_processor=url_processor,
        )

        self._url_commands = URLCommandsHandlerImpl(
            response_formatter=response_formatter,
            processor_provider=self,  # Pass self so handler can access current processor values
        )

        self._content = ContentHandlerImpl(
            response_formatter=response_formatter,
            summary_repo=self.summary_repo,
            llm_repo=self.llm_repo,
            container=container,
        )

        self._search = SearchHandlerImpl(
            response_formatter=response_formatter,
            searcher_provider=self,  # Pass self so handler can access current searcher values
            container=container,
        )

        self._karakeep = KarakeepHandlerImpl(
            cfg=cfg,
            db=db,
            response_formatter=response_formatter,
        )

        self._settings = SettingsHandlerImpl(
            verbosity_resolver=verbosity_resolver,
        )

    def _build_context(
        self,
        message: Any,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
        text: str = "",
    ) -> CommandExecutionContext:
        """Build execution context for command handlers.

        Args:
            message: The Pyrogram message object.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
            text: Message text (optional).

        Returns:
            A populated CommandExecutionContext instance.
        """
        return CommandExecutionContext.from_handler_args(
            message=message,
            uid=uid,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            start_time=start_time,
            user_repo=self.user_repo,
            response_formatter=self.response_formatter,
            audit_func=self._audit,
            text=text,
        )

    # =========================================================================
    # Onboarding delegation
    # =========================================================================

    async def handle_start_command(
        self,
        message: Any,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /start command.

        Args:
            message: The Pyrogram message object.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
        """
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time)
        await self._onboarding.handle_start(ctx)

    async def handle_help_command(
        self,
        message: Any,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /help command.

        Args:
            message: The Pyrogram message object.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
        """
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time)
        await self._onboarding.handle_help(ctx)

    # =========================================================================
    # Admin delegation
    # =========================================================================

    async def handle_dbinfo_command(
        self,
        message: Any,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /dbinfo command.

        Args:
            message: The Pyrogram message object.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
        """
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time)
        await self._admin.handle_dbinfo(ctx)

    async def handle_dbverify_command(
        self,
        message: Any,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /dbverify command.

        Args:
            message: The Pyrogram message object.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
        """
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time)
        await self._admin.handle_dbverify(ctx)

    async def handle_clearcache_command(
        self,
        message: Any,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /clearcache command.

        Args:
            message: The Pyrogram message object.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
        """
        from app.db.user_interactions import async_safe_update_user_interaction

        try:
            count = await self.url_processor.clear_cache()
            await self.response_formatter.safe_reply(
                message, f"✅ Cache cleared. Removed {count} keys."
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.user_repo,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="cache_cleared",
                    start_time=start_time,
                    logger_=logger,
                )
        except Exception as exc:
            logger.error("cache_clear_failed", extra={"error": str(exc), "uid": uid})
            await self.response_formatter.safe_reply(message, f"❌ Failed to clear cache: {exc}")
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.user_repo,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message=str(exc),
                    start_time=start_time,
                    logger_=logger,
                )

    # =========================================================================
    # URL commands delegation
    # =========================================================================

    async def handle_summarize_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> tuple[str | None, bool]:
        """Handle /summarize command.

        Args:
            message: The Pyrogram message object.
            text: The message text.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.

        Returns:
            Tuple of (next_action, should_continue).
        """
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        return await self._url_commands.handle_summarize(ctx)

    async def handle_summarize_all_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /summarize_all command.

        Args:
            message: The Pyrogram message object.
            text: The message text.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
        """
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._url_commands.handle_summarize_all(ctx)

    async def handle_cancel_command(
        self,
        message: Any,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /cancel command.

        Args:
            message: The Pyrogram message object.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
        """
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time)
        await self._url_commands.handle_cancel(ctx)

    # =========================================================================
    # Content delegation
    # =========================================================================

    async def handle_unread_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /unread command.

        Args:
            message: The Pyrogram message object.
            text: The message text.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
        """
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._content.handle_unread(ctx)

    async def handle_read_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /read <request_id> command.

        Args:
            message: The Pyrogram message object.
            text: The message text.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
        """
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._content.handle_read(ctx)

    # =========================================================================
    # Search delegation
    # =========================================================================

    async def handle_find_online_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
        *,
        command: str,
    ) -> None:
        """Handle Firecrawl-backed search commands.

        Args:
            message: The Pyrogram message object.
            text: The message text.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
            command: The command that triggered this handler.
        """
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._search.handle_find_online(ctx, command=command)

    async def handle_find_local_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
        *,
        command: str,
    ) -> None:
        """Handle database-only topic search commands.

        Args:
            message: The Pyrogram message object.
            text: The message text.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
            command: The command that triggered this handler.
        """
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._search.handle_find_local(ctx, command=command)

    async def handle_search_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /search command - hybrid semantic + keyword search.

        Args:
            message: The Pyrogram message object.
            text: The message text.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
        """
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._search.handle_search(ctx)

    # =========================================================================
    # Karakeep delegation
    # =========================================================================

    async def handle_sync_karakeep_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /sync_karakeep command.

        Args:
            message: The Pyrogram message object.
            text: The message text.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
        """
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._karakeep.handle_sync_karakeep(ctx)

    # =========================================================================
    # Settings delegation
    # =========================================================================

    async def handle_debug_command(
        self,
        message: Any,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /debug command -- toggle verbosity mode."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time)
        await self._settings.handle_debug(ctx)

    # =========================================================================
    # Static utilities (backward compatibility)
    # =========================================================================

    @staticmethod
    def _maybe_load_json(payload: Any) -> Any:
        """Load JSON from various formats.

        This method is kept for backward compatibility with any code that
        may reference it directly.

        Args:
            payload: The input payload in any format.

        Returns:
            The parsed JSON data, or None if parsing fails.
        """
        return maybe_load_json(payload)

    @staticmethod
    def _parse_unread_arguments(text: str | None) -> tuple[int, str | None]:
        """Parse optional limit and topic arguments from an /unread command string.

        This method is kept for backward compatibility with any code that
        may reference it directly.

        Args:
            text: The command text to parse.

        Returns:
            Tuple of (limit, topic) where limit defaults to 5 and topic may be None.
        """
        return ContentHandlerImpl.parse_unread_arguments(text)
