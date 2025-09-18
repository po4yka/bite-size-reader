"""Command processing for Telegram bot."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.config import AppConfig
from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import extract_all_urls

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.db.database import Database

logger = logging.getLogger(__name__)


class CommandProcessor:
    """Handles bot command processing."""

    def __init__(
        self,
        cfg: AppConfig,
        response_formatter: ResponseFormatter,
        db: Database,
        url_processor: URLProcessor,
        audit_func: Callable[[str, str, dict], None],
    ) -> None:
        self.cfg = cfg
        self.response_formatter = response_formatter
        self.db = db
        self.url_processor = url_processor
        self._audit = audit_func

    async def handle_start_command(
        self, message: Any, uid: int, correlation_id: str, interaction_id: int, start_time: float
    ) -> None:
        """Handle /start command."""
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_start",
            extra={"uid": uid, "chat_id": chat_id, "cid": correlation_id},
        )
        try:
            self._audit(
                "INFO", "command_start", {"uid": uid, "chat_id": chat_id, "cid": correlation_id}
            )
        except Exception:
            pass

        await self.response_formatter.send_welcome(message)
        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="welcome",
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    async def handle_help_command(
        self, message: Any, uid: int, correlation_id: str, interaction_id: int, start_time: float
    ) -> None:
        """Handle /help command."""
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_help",
            extra={"uid": uid, "chat_id": chat_id, "cid": correlation_id},
        )
        try:
            self._audit(
                "INFO", "command_help", {"uid": uid, "chat_id": chat_id, "cid": correlation_id}
            )
        except Exception:
            pass

        await self.response_formatter.send_help(message)
        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="help",
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    async def handle_dbinfo_command(
        self, message: Any, uid: int, correlation_id: str, interaction_id: int, start_time: float
    ) -> None:
        """Handle /dbinfo command."""
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_dbinfo",
            extra={"uid": uid, "chat_id": chat_id, "cid": correlation_id},
        )
        try:
            self._audit(
                "INFO", "command_dbinfo", {"uid": uid, "chat_id": chat_id, "cid": correlation_id}
            )
        except Exception:
            pass

        overview = self.db.get_database_overview()
        await self.response_formatter.send_db_overview(message, overview)
        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="dbinfo",
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    async def handle_summarize_all_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /summarize_all command."""
        urls = extract_all_urls(text)
        if len(urls) == 0:
            await self.response_formatter.safe_reply(
                message,
                "Send multiple URLs in one message after /summarize_all, separated by space or new line.",
            )
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message="No URLs found",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
            return

        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_summarize_all",
            extra={
                "uid": uid,
                "chat_id": chat_id,
                "cid": correlation_id,
                "count": len(urls),
            },
        )
        try:
            self._audit(
                "INFO",
                "command_summarize_all",
                {"uid": uid, "chat_id": chat_id, "cid": correlation_id, "count": len(urls)},
            )
        except Exception:
            pass

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
            logger.debug("processing_link", extra={"uid": uid, "url": u, "cid": per_link_cid})
            await self.url_processor.handle_url_flow(message, u, correlation_id=per_link_cid)

    async def handle_summarize_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> tuple[str | None, bool]:
        """Handle /summarize command. Returns (next_action, should_continue)."""
        urls = extract_all_urls(text)
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_summarize",
            extra={
                "uid": uid,
                "chat_id": chat_id,
                "cid": correlation_id,
                "with_urls": bool(urls),
                "count": len(urls),
            },
        )
        try:
            self._audit(
                "INFO",
                "command_summarize",
                {
                    "uid": uid,
                    "chat_id": chat_id,
                    "cid": correlation_id,
                    "with_urls": bool(urls),
                    "count": len(urls),
                },
            )
        except Exception:
            pass

        if len(urls) > 1:
            await self.response_formatter.safe_reply(
                message, f"Process {len(urls)} links? (yes/no)"
            )
            logger.debug("awaiting_multi_confirm", extra={"uid": uid, "count": len(urls)})
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="confirmation",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
            return "multi_confirm", False
        elif len(urls) == 1:
            await self.url_processor.handle_url_flow(
                message,
                urls[0],
                correlation_id=correlation_id,
                interaction_id=interaction_id,
            )
            return None, False
        else:
            await self.response_formatter.safe_reply(message, "Send a URL to summarize.")
            logger.debug("awaiting_url", extra={"uid": uid})
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="awaiting_url",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
            return "awaiting_url", False

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
            extra={"interaction_id": interaction_id, "response_type": response_type},
        )
