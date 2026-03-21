"""Telegram command dispatcher.

This module provides the TelegramCommandDispatcher class, which centralizes
command precedence and delegates concrete work to the existing handler
components. It keeps the old command-processor surface available for
compatibility while moving routing data into one place.

Handlers:
- OnboardingHandler: /start, /help
- AdminHandler: /admin, /dbinfo, /dbverify
- URLCommandsHandler: /summarize, /summarize_all, /cancel
- ContentHandler: /unread, /read
- SearchHandler: /find*, /search
- KarakeepHandler: /sync_karakeep
- RulesHandler: /rules
"""

# ruff: noqa: E501
# flake8: noqa

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.adapters.telegram.command_handlers.admin_handler import AdminHandler
from app.adapters.telegram.command_handlers.backup_handler import BackupHandler
from app.adapters.telegram.command_handlers.content_handler import ContentHandler
from app.adapters.telegram.command_handlers.digest_handler import DigestHandler
from app.adapters.telegram.command_handlers.execution_context import CommandExecutionContext
from app.adapters.telegram.command_handlers.export_command import ExportHandler
from app.adapters.telegram.command_handlers.init_session_handler import InitSessionHandler
from app.adapters.telegram.command_handlers.karakeep_handler import KarakeepHandler
from app.adapters.telegram.command_handlers.listen_handler import ListenHandler
from app.adapters.telegram.command_handlers.onboarding_handler import OnboardingHandler
from app.adapters.telegram.command_handlers.rules_handler import RulesHandler
from app.adapters.telegram.command_handlers.search_handler import SearchHandler
from app.adapters.telegram.command_handlers.settings_handler import SettingsHandler
from app.adapters.telegram.command_handlers.tag_handler import TagHandler
from app.adapters.telegram.command_handlers.url_commands_handler import URLCommandsHandler
from app.adapters.telegram.command_handlers.utils import maybe_load_json
from app.adapters.telegram.task_manager import UserTaskManager
from app.application.ports import (
    LLMRepositoryPort,
    RequestRepositoryPort,
    SummaryRepositoryPort,
    UserRepositoryPort,
)
from app.application.services.topic_search import LocalTopicSearchService, TopicSearchService
from app.config import AppConfig
from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.command_handlers.base_handler import HandlerDependenciesMixin
    from app.adapters.telegram.url_handler import URLHandler
    from app.db.session import DatabaseSessionManager
    from app.infrastructure.search.hybrid_search_service import HybridSearchService

logger = get_logger(__name__)


UidCommandHandler = Callable[[Any, int, str, int, float], Awaitable[None]]
TextCommandHandler = Callable[[Any, str, int, str, int, float], Awaitable[None]]
AliasCommandHandler = Callable[..., Awaitable[None]]

_LOCAL_SEARCH_ALIASES: tuple[str, ...] = ("/finddb", "/findlocal")
_ONLINE_SEARCH_ALIASES: tuple[str, ...] = ("/findweb", "/findonline", "/find")


@dataclass(frozen=True, slots=True)
class CommandDispatchOutcome:
    handled: bool
    next_action: str | None = None


class TelegramCommandDispatcher:
    """Handle Telegram bot commands and dispatch them by precedence.

    The dispatcher keeps the legacy command-processor methods for compatibility,
    but the main runtime now routes through :meth:`dispatch_command`.
    """

    def __init__(
        self,
        cfg: AppConfig,
        response_formatter: ResponseFormatter,
        db: DatabaseSessionManager,
        url_processor: URLProcessor,
        audit_func: Callable[[str, str, dict], None],
        *,
        url_handler: URLHandler | None = None,
        topic_searcher: TopicSearchService | None = None,
        local_searcher: LocalTopicSearchService | None = None,
        task_manager: UserTaskManager | None = None,
        hybrid_search: HybridSearchService | None = None,
        verbosity_resolver: Any | None = None,
        user_repo: UserRepositoryPort,
        summary_repo: SummaryRepositoryPort,
        request_repo: RequestRepositoryPort,
        llm_repo: LLMRepositoryPort,
        application_services: Any | None = None,
        handlers: dict[str, Any] | None = None,
    ) -> None:
        self.cfg = cfg
        self.response_formatter = response_formatter
        self.db = db
        self._audit = audit_func

        self.user_repo = user_repo
        self.summary_repo = summary_repo
        self.request_repo = request_repo
        self.llm_repo = llm_repo

        self.url_processor = url_processor
        self.url_handler: URLHandler | None = url_handler
        self.topic_searcher = topic_searcher
        self.local_searcher = local_searcher
        self._task_manager = task_manager
        self._application_services = application_services
        self._verbosity_resolver = verbosity_resolver
        self.hybrid_search = hybrid_search

        wired_handlers = handlers or self._build_default_handlers()
        self._onboarding = self._require_handler(wired_handlers, "onboarding", OnboardingHandler)
        self._admin = self._require_handler(wired_handlers, "admin", AdminHandler)
        self._url_commands = self._require_handler(
            wired_handlers,
            "url_commands",
            URLCommandsHandler,
        )
        self._content = self._require_handler(wired_handlers, "content", ContentHandler)
        self._search = self._require_handler(wired_handlers, "search", SearchHandler)
        self._karakeep = self._require_handler(wired_handlers, "karakeep", KarakeepHandler)
        self._listen = self._require_handler(wired_handlers, "listen", ListenHandler)
        self._digest = self._require_handler(wired_handlers, "digest", DigestHandler)
        self._init_session = self._require_handler(
            wired_handlers,
            "init_session",
            InitSessionHandler,
        )
        self._settings = self._require_handler(wired_handlers, "settings", SettingsHandler)
        self._tag = self._require_handler(wired_handlers, "tag", TagHandler)
        self._rules = self._require_handler(wired_handlers, "rules", RulesHandler)
        self._export = self._require_handler(wired_handlers, "export", ExportHandler)
        self._backup = self._require_handler(wired_handlers, "backup", BackupHandler)

        self._pre_alias_uid_commands: tuple[tuple[str, UidCommandHandler], ...] = (
            ("/start", self.handle_start_command),
            ("/help", self.handle_help_command),
            ("/dbinfo", self.handle_dbinfo_command),
            ("/dbverify", self.handle_dbverify_command),
            ("/clearcache", self.handle_clearcache_command),
        )
        self._pre_alias_text_commands: tuple[tuple[str, TextCommandHandler], ...] = (
            ("/admin", self.handle_admin_command),
        )
        self._pre_summarize_text_commands: tuple[tuple[str, TextCommandHandler], ...] = (
            ("/summarize_all", self.handle_summarize_all_command),
        )
        self._post_summarize_uid_commands: tuple[tuple[str, UidCommandHandler], ...] = (
            ("/cancel", self.handle_cancel_command),
        )
        self._post_summarize_text_commands: tuple[tuple[str, TextCommandHandler], ...] = (
            ("/untag", self.handle_untag_command),
            ("/tags", self.handle_tags_command),
            ("/tag", self.handle_tag_command),
            ("/unread", self.handle_unread_command),
            ("/read", self.handle_read_command),
            ("/search", self.handle_search_command),
            ("/sync_karakeep", self.handle_sync_karakeep_command),
            ("/listen", self.handle_listen_command),
            ("/cdigest", self.handle_cdigest_command),
            ("/digest", self.handle_digest_command),
            ("/channels", self.handle_channels_command),
            ("/subscribe", self.handle_subscribe_command),
            ("/unsubscribe", self.handle_unsubscribe_command),
            ("/init_session", self.handle_init_session_command),
            ("/settings", self.handle_settings_command),
            ("/rules", self.handle_rules_command),
            ("/export", self.handle_export_command),
            ("/backups", self.handle_backups_command),
            ("/backup", self.handle_backup_command),
        )
        self._tail_uid_commands: tuple[tuple[str, UidCommandHandler], ...] = (
            ("/debug", self.handle_debug_command),
        )

    def _build_default_handlers(self) -> dict[str, Any]:
        return {
            "onboarding": OnboardingHandler(self.response_formatter),
            "admin": AdminHandler(
                db=self.db,
                response_formatter=self.response_formatter,
                url_processor=self.url_processor,
                url_handler=self.url_handler,
            ),
            "url_commands": URLCommandsHandler(
                response_formatter=self.response_formatter,
                processor_provider=self,
            ),
            "content": ContentHandler(
                response_formatter=self.response_formatter,
                summary_repo=self.summary_repo,
                llm_repo=self.llm_repo,
                unread_summaries_use_case=getattr(
                    self._application_services,
                    "unread_summaries",
                    None,
                ),
                mark_summary_as_read_use_case=getattr(
                    self._application_services,
                    "mark_summary_as_read",
                    None,
                ),
                event_bus=getattr(self._application_services, "event_bus", None),
            ),
            "search": SearchHandler(
                response_formatter=self.response_formatter,
                searcher_provider=self,
                search_topics_use_case=getattr(self._application_services, "search_topics", None),
            ),
            "karakeep": KarakeepHandler(
                cfg=self.cfg,
                db=self.db,
                response_formatter=self.response_formatter,
            ),
            "listen": ListenHandler(
                cfg=self.cfg,
                db=self.db,
                response_formatter=self.response_formatter,
            ),
            "digest": DigestHandler(
                cfg=self.cfg,
                db=self.db,
                response_formatter=self.response_formatter,
            ),
            "init_session": InitSessionHandler(
                cfg=self.cfg,
                response_formatter=self.response_formatter,
            ),
            "settings": SettingsHandler(
                verbosity_resolver=self._verbosity_resolver,
                cfg=self.cfg,
            ),
            "tag": TagHandler(
                cfg=self.cfg,
                db=self.db,
                response_formatter=self.response_formatter,
            ),
            "rules": RulesHandler(
                cfg=self.cfg,
                db=self.db,
                response_formatter=self.response_formatter,
            ),
            "export": ExportHandler(
                cfg=self.cfg,
                db=self.db,
                response_formatter=self.response_formatter,
            ),
            "backup": BackupHandler(
                cfg=self.cfg,
                db=self.db,
                response_formatter=self.response_formatter,
            ),
        }

    @staticmethod
    def _require_handler(handlers: dict[str, Any], key: str, _expected_type: type[Any]) -> Any:
        handler = handlers.get(key)
        if handler is None:
            raise RuntimeError(f"Missing command handler: {key}")
        return handler

    async def dispatch_command(
        self,
        *,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> CommandDispatchOutcome:
        if not text.startswith("/"):
            return CommandDispatchOutcome(handled=False)

        if await self._dispatch_uid_command(
            text,
            self._pre_alias_uid_commands,
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return CommandDispatchOutcome(handled=True)

        if await self._dispatch_text_command(
            text,
            self._pre_alias_text_commands,
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return CommandDispatchOutcome(handled=True)

        if await self._dispatch_alias_command(
            text,
            _LOCAL_SEARCH_ALIASES,
            self.handle_find_local_command,
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return CommandDispatchOutcome(handled=True)

        if await self._dispatch_alias_command(
            text,
            _ONLINE_SEARCH_ALIASES,
            self.handle_find_online_command,
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return CommandDispatchOutcome(handled=True)

        if await self._dispatch_text_command(
            text,
            self._pre_summarize_text_commands,
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return CommandDispatchOutcome(handled=True)

        summarize_outcome = await self._dispatch_summarize_command(
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        )
        if summarize_outcome.handled:
            return summarize_outcome

        if await self._dispatch_uid_command(
            text,
            self._post_summarize_uid_commands,
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return CommandDispatchOutcome(handled=True)

        if await self._dispatch_text_command(
            text,
            self._post_summarize_text_commands,
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return CommandDispatchOutcome(handled=True)

        if await self._dispatch_uid_command(
            text,
            self._tail_uid_commands,
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return CommandDispatchOutcome(handled=True)

        return CommandDispatchOutcome(handled=False)

    async def _dispatch_uid_command(
        self,
        route_probe: str,
        handlers: tuple[tuple[str, UidCommandHandler], ...],
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        _ = text
        for prefix, handler in handlers:
            if route_probe.startswith(prefix):
                await handler(message, uid, correlation_id, interaction_id, start_time)
                return True
        return False

    async def _dispatch_text_command(
        self,
        route_probe: str,
        handlers: tuple[tuple[str, TextCommandHandler], ...],
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        for prefix, handler in handlers:
            if route_probe.startswith(prefix):
                await handler(message, text, uid, correlation_id, interaction_id, start_time)
                return True
        return False

    async def _dispatch_alias_command(
        self,
        route_probe: str,
        aliases: tuple[str, ...],
        handler: AliasCommandHandler,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        matched_alias = self._match_prefix(route_probe, aliases)
        if matched_alias is None:
            return False

        await handler(
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
            command=matched_alias,
        )
        return True

    async def _dispatch_summarize_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> CommandDispatchOutcome:
        if not text.startswith("/summarize"):
            return CommandDispatchOutcome(handled=False)

        action, _should_continue = await self.handle_summarize_command(
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        )
        if action == "awaiting_url" and self.url_handler is not None:
            await self.url_handler.add_awaiting_user(uid)
        return CommandDispatchOutcome(handled=True, next_action=action)

    @staticmethod
    def _match_prefix(text: str, prefixes: tuple[str, ...]) -> str | None:
        for prefix in prefixes:
            if text.startswith(prefix):
                return prefix
        return None

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

    async def handle_admin_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /admin command with subcommands.

        Args:
            message: The Pyrogram message object.
            text: The message text.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
        """
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._admin.handle_admin(ctx)

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
            if self.url_handler is None:
                msg = "URL handler is unavailable"
                raise RuntimeError(msg)
            count = await self.url_handler.clear_extraction_cache()
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
    # Listen (TTS) delegation
    # =========================================================================

    async def handle_listen_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /listen command -- generate audio from a summary."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._listen.handle_listen(ctx)

    # =========================================================================
    # Digest delegation
    # =========================================================================

    async def handle_cdigest_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /cdigest command -- single-channel unread digest."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._digest.handle_cdigest(ctx)

    async def handle_digest_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /digest command."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._digest.handle_digest(ctx)

    async def handle_channels_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /channels command."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._digest.handle_channels(ctx)

    async def handle_subscribe_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /subscribe command."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._digest.handle_subscribe(ctx)

    async def handle_unsubscribe_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /unsubscribe command."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._digest.handle_unsubscribe(ctx)

    # =========================================================================
    # Init session delegation
    # =========================================================================

    async def handle_init_session_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /init_session command."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._init_session.handle_init_session(ctx)

    async def handle_init_session_contact(self, message: Any) -> None:
        """Handle contact message during session init flow."""
        await self._init_session.handle_contact(message)

    async def handle_init_session_webapp(self, message: Any) -> None:
        """Handle web_app_data message during session init flow."""
        await self._init_session.handle_web_app_data(message)

    def has_active_init_session(self, uid: int) -> bool:
        """Check if user has an active session init flow."""
        return self._init_session.has_active_session(uid)

    # =========================================================================
    # Tag delegation
    # =========================================================================

    async def handle_tag_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /tag command -- add a tag to a summary."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._tag.handle_tag(ctx)

    async def handle_untag_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /untag command -- remove a tag from a summary."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._tag.handle_untag(ctx)

    async def handle_tags_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /tags command -- list tags or summaries for a tag."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._tag.handle_tags(ctx)

    # =========================================================================
    # Rules delegation
    # =========================================================================

    async def handle_rules_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /rules command -- list automation rules."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._rules.handle_rules(ctx)

    # =========================================================================
    # Export delegation
    # =========================================================================

    async def handle_export_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /export command -- export summaries as a file."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._export.handle_export(ctx)

    # =========================================================================
    # Backup delegation
    # =========================================================================

    async def handle_backup_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /backup command -- create and send a backup."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._backup.handle_backup(ctx)

    async def handle_backups_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /backups command -- list recent backups."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._backup.handle_backups(ctx)

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

    async def handle_settings_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /settings command -- open digest Mini App."""
        ctx = self._build_context(message, uid, correlation_id, interaction_id, start_time, text)
        await self._settings.handle_settings(ctx)

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
        return ContentHandler.parse_unread_arguments(text)
