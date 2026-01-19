"""Execution context for command handlers.

This module provides the CommandExecutionContext dataclass that bundles
all parameters needed by command handlers, reducing parameter duplication
across handler methods.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.external.response_formatter import ResponseFormatter
    from app.infrastructure.persistence.sqlite.repositories.user_repository import (
        SqliteUserRepositoryAdapter,
    )

logger = logging.getLogger(__name__)


@dataclass
class CommandExecutionContext:
    """Context object containing all information needed to execute a command.

    This context bundles common parameters that are passed to every command handler,
    reducing repetitive parameter lists and providing a single point for shared data.

    Attributes:
        message: The Pyrogram message object.
        text: The message text content.
        uid: The user ID who sent the message.
        chat_id: The chat ID where the message was sent (may be None).
        correlation_id: Unique ID for tracing this request through logs.
        interaction_id: Database ID for the user interaction record.
        start_time: Timestamp when processing started (for latency tracking).
        user_repo: Repository for user data persistence.
        response_formatter: Formatter for sending responses.
        audit_func: Callback function for audit logging.
    """

    message: Any
    text: str
    uid: int
    chat_id: int | None
    correlation_id: str
    interaction_id: int
    start_time: float
    user_repo: SqliteUserRepositoryAdapter
    response_formatter: ResponseFormatter
    audit_func: Callable[[str, str, dict[str, Any]], None]

    # Optional fields with defaults
    has_forward: bool = field(default=False)

    @classmethod
    def from_handler_args(
        cls,
        *,
        message: Any,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
        user_repo: SqliteUserRepositoryAdapter,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict[str, Any]], None],
        text: str = "",
    ) -> CommandExecutionContext:
        """Create context from handler arguments.

        This factory method extracts chat_id from the message and creates
        a fully populated context object.

        Args:
            message: The Pyrogram message object.
            uid: The user ID.
            correlation_id: Request correlation ID.
            interaction_id: Database interaction ID.
            start_time: Processing start timestamp.
            user_repo: User repository instance.
            response_formatter: Response formatter instance.
            audit_func: Audit logging callback.
            text: Message text (optional, extracted from message if empty).

        Returns:
            A populated CommandExecutionContext instance.
        """
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        if not text:
            text = getattr(message, "text", "") or ""

        return cls(
            message=message,
            text=text,
            uid=uid,
            chat_id=chat_id,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            start_time=start_time,
            user_repo=user_repo,
            response_formatter=response_formatter,
            audit_func=audit_func,
        )

    def log_extra(self, **extra: Any) -> dict[str, Any]:
        """Build extra dict for structured logging.

        Returns a dictionary with common context fields plus any additional
        fields provided.

        Args:
            **extra: Additional key-value pairs to include.

        Returns:
            Dictionary suitable for logger.info(..., extra=result).
        """
        base = {
            "uid": self.uid,
            "chat_id": self.chat_id,
            "cid": self.correlation_id,
        }
        base.update(extra)
        return base
