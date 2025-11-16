"""Access control for Telegram bot messages."""

from __future__ import annotations

import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any

from app.db.user_interactions import async_safe_update_user_interaction

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.external.response_formatter import ResponseFormatter
    from app.config import AppConfig
    from app.db.database import Database

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
            msg = "Telegram access control requires ALLOWED_USER_IDS to be configured."
            raise RuntimeError(msg)

        # Security tracking
        self._failed_attempts: dict[int, int] = {}
        self._last_attempt_time: dict[int, float] = {}
        self._block_notified_until: dict[int, float] = {}
        self._deny_notified_until: dict[int, float] = {}
        self.MAX_FAILED_ATTEMPTS = 3
        self.BLOCK_DURATION_SECONDS = 300  # 5 minutes
        self.DENY_NOTIFICATION_COOLDOWN_SECONDS = 300

    async def check_access(
        self, uid: int, message: Any, correlation_id: str, interaction_id: int, start_time: float
    ) -> bool:
        """Check if user has access to the bot."""
        allowed_ids = self.cfg.telegram.allowed_user_ids

        current_time = time.time()

        if uid in allowed_ids:
            # Reset failed attempts on successful access
            self._failed_attempts.pop(uid, None)
            self._last_attempt_time.pop(uid, None)
            self._block_notified_until.pop(uid, None)
            self._deny_notified_until.pop(uid, None)
            logger.info("access_granted", extra={"uid": uid})
            return True

        # Check if user is blocked due to too many failed attempts (unauthorized users only)
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
                await self._maybe_notify_blocked(uid, message, current_time)
                return False

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
            await self._maybe_notify_blocked(
                uid,
                message,
                current_time,
                force=True,
                message_text=(
                    f"❌ Access blocked after {failed_count} failed attempts. "
                    f"Try again in {self.BLOCK_DURATION_SECONDS // 60} minutes."
                ),
            )
            return False

        with contextlib.suppress(Exception):
            self._audit("WARN", "access_denied", {"uid": uid, "cid": correlation_id})

        if await self._maybe_notify_denied(uid, message, current_time):
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

    async def _maybe_notify_blocked(
        self,
        uid: int,
        message: Any,
        current_time: float,
        *,
        force: bool = False,
        message_text: str | None = None,
    ) -> None:
        """Send block notification at most once per block window."""
        deadline = self._block_notified_until.get(uid, 0.0)
        if force or current_time >= deadline:
            with contextlib.suppress(Exception):
                await self.response_formatter.safe_reply(
                    message,
                    message_text
                    or "❌ Access temporarily blocked due to too many failed attempts. Please try again later.",
                )
            self._block_notified_until[uid] = current_time + self.BLOCK_DURATION_SECONDS

    async def _maybe_notify_denied(self, uid: int, message: Any, current_time: float) -> bool:
        """Send access denied notification with cooldown."""
        deadline = self._deny_notified_until.get(uid, 0.0)
        if current_time < deadline:
            return False

        with contextlib.suppress(Exception):
            await self.response_formatter.safe_reply(
                message,
                f"❌ Access denied. User ID {uid} is not authorized to use this bot.",
            )
        self._deny_notified_until[uid] = current_time + self.DENY_NOTIFICATION_COOLDOWN_SECONDS
        return True
