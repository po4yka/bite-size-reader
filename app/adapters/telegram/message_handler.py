"""Refactored message handler using modular components."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.adapters.telegram.access_controller import AccessController
from app.adapters.telegram.command_processor import CommandProcessor
from app.adapters.telegram.message_router import MessageRouter
from app.adapters.telegram.task_manager import UserTaskManager
from app.adapters.telegram.url_handler import URLHandler
from app.config import AppConfig
from app.db.database import Database

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.forward_processor import ForwardProcessor

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
            task_manager=self.task_manager,
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

    def _audit(self, level: str, event: str, details: dict) -> None:
        """Audit log helper."""
        try:
            self.db.insert_audit_log(level=level, event=event, details_json=details)
        except Exception as e:  # noqa: BLE001
            logger.error("audit_persist_failed", extra={"error": str(e), "event": event})
