"""Refactored message handler using modular components."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.adapters.telegram.access_controller import AccessController
from app.adapters.telegram.command_processor import CommandProcessor
from app.adapters.telegram.message_router import MessageRouter
from app.adapters.telegram.task_manager import UserTaskManager
from app.adapters.telegram.url_handler import URLHandler

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.forward_processor import ForwardProcessor
    from app.config import AppConfig
    from app.db.database import Database
    from app.services.topic_search import LocalTopicSearchService, TopicSearchService

logger = logging.getLogger(__name__)


class MessageHandler:
    """Refactored message handler using modular components."""

    def __init__(
        self,
        cfg: AppConfig,
        db: Database,
        response_formatter: ResponseFormatter,
        url_processor: URLProcessor,
        forward_processor: ForwardProcessor,
        topic_searcher: TopicSearchService | None = None,
        local_searcher: LocalTopicSearchService | None = None,
        container: Any | None = None,
    ) -> None:
        self.cfg = cfg
        self.db = db

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
        )

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

            # Handle multi-link confirmation callbacks
            if callback_data == "multi_confirm_yes":
                await self._handle_multi_confirm_yes(message, uid)
            elif callback_data == "multi_confirm_no":
                await self._handle_multi_confirm_no(message, uid)
            else:
                logger.warning("unknown_callback_data", extra={"data": callback_data})

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
        """Audit log helper."""
        try:
            self.db.insert_audit_log(level=level, event=event, details_json=details)
        except Exception as e:
            logger.exception("audit_persist_failed", extra={"error": str(e), "event": event})
