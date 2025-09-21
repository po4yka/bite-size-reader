"""Access control for Telegram bot messages."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.config import AppConfig

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


class AccessController:
    """Handles access control and user validation."""

    def __init__(
        self,
        cfg: AppConfig,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
    ) -> None:
        self.cfg = cfg
        self.response_formatter = response_formatter
        self._audit = audit_func

        if not self.cfg.telegram.allowed_user_ids:
            raise RuntimeError(
                "Telegram access control requires ALLOWED_USER_IDS to be configured."
            )

    async def check_access(
        self, uid: int, message: Any, correlation_id: str, interaction_id: int, start_time: float
    ) -> bool:
        """Check if user has access to the bot."""
        allowed_ids = self.cfg.telegram.allowed_user_ids

        if uid in allowed_ids:
            logger.info("access_granted", extra={"uid": uid})
            return True

        logger.warning(
            "access_denied_list_mismatch",
            extra={"uid": uid, "allowed_count": len(allowed_ids)},
        )
        try:
            self._audit("WARN", "access_denied", {"uid": uid, "cid": correlation_id})
        except Exception:
            pass

        await self.response_formatter.safe_reply(
            message,
            f"This bot is private. Access denied. Error ID: {correlation_id}",
        )
        logger.info("access_denied", extra={"uid": uid, "cid": correlation_id})

        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="error",
                error_occurred=True,
                error_message="Access denied",
                processing_time_ms=int((time.time() - start_time) * 1000),
            )
        return False

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
