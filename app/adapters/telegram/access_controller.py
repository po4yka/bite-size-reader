"""Access control for Telegram bot messages."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.config import AppConfig
from app.db.database import Database
from app.db.user_interactions import async_safe_update_user_interaction

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


class AccessController:
    """Handles access control and user validation."""

    def __init__(
        self,
        cfg: AppConfig,
        db: Database,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.response_formatter = response_formatter
        self._audit = audit_func

        if not self.cfg.telegram.allowed_user_ids:
            raise RuntimeError(
                "Telegram access control requires ALLOWED_USER_IDS to be configured."
            )

        # Security tracking
        self._failed_attempts: dict[int, int] = {}
        self._last_attempt_time: dict[int, float] = {}
        self.MAX_FAILED_ATTEMPTS = 3
        self.BLOCK_DURATION_SECONDS = 300  # 5 minutes

    async def check_access(
        self, uid: int, message: Any, correlation_id: str, interaction_id: int, start_time: float
    ) -> bool:
        """Check if user has access to the bot."""
        allowed_ids = self.cfg.telegram.allowed_user_ids

        # Check if user is blocked due to too many failed attempts
        current_time = time.time()
        if uid in self._last_attempt_time:
            time_since_last_attempt = current_time - self._last_attempt_time[uid]
            if time_since_last_attempt < self.BLOCK_DURATION_SECONDS:
                logger.warning(
                    "access_blocked_rate_limited",
                    extra={
                        "uid": uid,
                        "time_remaining": self.BLOCK_DURATION_SECONDS - time_since_last_attempt,
                        "failed_attempts": self._failed_attempts.get(uid, 0),
                    },
                )
                try:
                    await self.response_formatter.safe_reply(
                        message,
                        "❌ Access temporarily blocked due to too many failed attempts. Please try again later.",
                    )
                except Exception:
                    pass
                return False

        if uid in allowed_ids:
            # Reset failed attempts on successful access
            self._failed_attempts.pop(uid, None)
            self._last_attempt_time.pop(uid, None)
            logger.info("access_granted", extra={"uid": uid})
            return True

        # Track failed attempts
        self._failed_attempts[uid] = self._failed_attempts.get(uid, 0) + 1
        self._last_attempt_time[uid] = current_time

        failed_count = self._failed_attempts[uid]
        logger.warning(
            "access_denied_list_mismatch",
            extra={
                "uid": uid,
                "allowed_count": len(allowed_ids),
                "failed_attempts": failed_count,
                "max_attempts": self.MAX_FAILED_ATTEMPTS,
            },
        )

        # Block user after too many failed attempts
        if failed_count >= self.MAX_FAILED_ATTEMPTS:
            logger.warning(
                "access_blocked_too_many_attempts",
                extra={
                    "uid": uid,
                    "failed_attempts": failed_count,
                    "block_duration_seconds": self.BLOCK_DURATION_SECONDS,
                },
            )
            try:
                await self.response_formatter.safe_reply(
                    message,
                    f"❌ Access blocked after {failed_count} failed attempts. "
                    f"Try again in {self.BLOCK_DURATION_SECONDS // 60} minutes.",
                )
            except Exception:
                pass
            return False

        try:
            self._audit("WARN", "access_denied", {"uid": uid, "cid": correlation_id})
        except Exception:
            pass

        await self.response_formatter.safe_reply(
            message,
            f"❌ Access denied. User ID {uid} is not authorized to use this bot.",
        )
        logger.info("access_denied", extra={"uid": uid, "cid": correlation_id})

        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="error",
                error_occurred=True,
                error_message="Access denied",
                start_time=start_time,
                logger_=logger,
            )
        return False
