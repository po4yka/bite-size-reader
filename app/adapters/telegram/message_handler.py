"""Refactored message handler using modular components."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.adapters.telegram.access_controller import AccessController
from app.adapters.telegram.callback_handler import CallbackHandler
from app.adapters.telegram.command_processor import CommandProcessor
from app.adapters.telegram.message_router import MessageRouter
from app.adapters.telegram.task_manager import UserTaskManager
from app.adapters.telegram.url_handler import URLHandler
from app.infrastructure.persistence.sqlite.repositories.audit_log_repository import (
    SqliteAuditLogRepositoryAdapter,
)

if TYPE_CHECKING:
    from app.adapters.attachment.attachment_processor import AttachmentProcessor
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.forward_processor import ForwardProcessor
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager
    from app.services.adaptive_timeout import AdaptiveTimeoutService
    from app.services.hybrid_search_service import HybridSearchService
    from app.services.topic_search import LocalTopicSearchService, TopicSearchService

logger = logging.getLogger(__name__)


class MessageHandler:
    """Refactored message handler using modular components."""

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        response_formatter: ResponseFormatter,
        url_processor: URLProcessor,
        forward_processor: ForwardProcessor,
        topic_searcher: TopicSearchService | None = None,
        local_searcher: LocalTopicSearchService | None = None,
        container: Any | None = None,
        hybrid_search: HybridSearchService | None = None,
        attachment_processor: AttachmentProcessor | None = None,
        verbosity_resolver: Any | None = None,
        adaptive_timeout_service: AdaptiveTimeoutService | None = None,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.audit_repo = SqliteAuditLogRepositoryAdapter(db)

        # Initialize components
        self.task_manager = UserTaskManager()
        self.access_controller = AccessController(
            cfg=cfg,
            db=db,
            response_formatter=response_formatter,
            audit_func=self._audit,
        )

        self.url_handler = URLHandler(
            db=db,
            response_formatter=response_formatter,
            url_processor=url_processor,
            adaptive_timeout_service=adaptive_timeout_service,
        )
        # Expose url_processor for legacy integrations/tests
        self.url_processor = url_processor

        self.command_processor = CommandProcessor(
            cfg=cfg,
            response_formatter=response_formatter,
            db=db,
            url_processor=url_processor,
            audit_func=self._audit,
            url_handler=self.url_handler,
            topic_searcher=topic_searcher,
            local_searcher=local_searcher,
            task_manager=self.task_manager,
            container=container,
            hybrid_search=hybrid_search,
            verbosity_resolver=verbosity_resolver,
        )

        self.message_router = MessageRouter(
            cfg=cfg,
            db=db,
            access_controller=self.access_controller,
            command_processor=self.command_processor,
            url_handler=self.url_handler,
            forward_processor=forward_processor,
            response_formatter=response_formatter,
            audit_func=self._audit,
            task_manager=self.task_manager,
            attachment_processor=attachment_processor,
        )

        # Initialize callback handler for post-summary actions
        self.callback_handler = CallbackHandler(
            db=db,
            response_formatter=response_formatter,
            url_handler=self.url_handler,
        )

    async def handle_message(self, message: Any) -> None:
        """Main message handling entry point."""
        await self.message_router.route_message(message)

    async def handle_callback_query(self, callback_query: Any) -> None:
        """Handle inline button callback queries."""
        try:
            # Extract callback data and user info
            data = getattr(callback_query, "data", None)
            from_user = getattr(callback_query, "from_user", None)
            message = getattr(callback_query, "message", None)

            if not data or not from_user or not message:
                logger.warning("invalid_callback_query", extra={"has_data": data is not None})
                return

            uid = from_user.id
            callback_data = data.decode() if isinstance(data, bytes) else str(data)

            logger.info(
                "callback_query_received",
                extra={"uid": uid, "data": callback_data},
            )

            # Answer the callback query to remove the loading state
            try:
                await callback_query.answer()
            except Exception as e:
                logger.warning("callback_answer_failed", extra={"error": str(e)})

            # Handle multi-link confirmation callbacks (legacy path)
            if callback_data == "multi_confirm_yes":
                await self._handle_multi_confirm_yes(message, uid)
                return
            if callback_data == "multi_confirm_no":
                await self._handle_multi_confirm_no(message, uid)
                return

            # Route to the unified callback handler for all other actions
            handled = await self.callback_handler.handle_callback(
                callback_query, uid, callback_data
            )
            if not handled:
                logger.warning("unhandled_callback_data", extra={"data": callback_data})

        except Exception as e:
            logger.exception("callback_query_handler_failed", extra={"error": str(e)})

    async def _handle_multi_confirm_yes(self, message: Any, uid: int) -> None:
        """Handle 'Yes' confirmation for multi-link processing."""
        # Simulate typing "yes" text message to trigger existing flow
        # This reuses the existing multi-link confirmation logic
        await self.message_router.handle_multi_confirm_response(message, uid, "yes")

    async def _handle_multi_confirm_no(self, message: Any, uid: int) -> None:
        """Handle 'No' confirmation for multi-link processing."""
        # Simulate typing "no" text message to trigger existing flow
        await self.message_router.handle_multi_confirm_response(message, uid, "no")

    def _audit(self, level: str, event: str, details: dict) -> None:
        """Audit log helper (background async)."""
        import asyncio

        async def _do_audit() -> None:
            try:
                await self.audit_repo.async_insert_audit_log(
                    log_level=level, event_type=event, details=details
                )
            except Exception as e:
                logger.warning("audit_persist_failed", extra={"error": str(e), "event": event})

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_do_audit())
            if not hasattr(self, "_audit_tasks"):
                self._audit_tasks: set[asyncio.Task] = set()
            self._audit_tasks.add(task)
            task.add_done_callback(self._audit_tasks.discard)
        except RuntimeError:
            pass
