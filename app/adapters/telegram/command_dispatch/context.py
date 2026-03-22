"""Context factory for Telegram command handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adapters.telegram.command_handlers.execution_context import CommandExecutionContext


@dataclass(frozen=True, slots=True)
class CommandContextFactory:
    user_repo: Any
    response_formatter: Any
    audit_func: Any

    def build(
        self,
        *,
        message: Any,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
        text: str = "",
    ) -> CommandExecutionContext:
        return CommandExecutionContext.from_handler_args(
            message=message,
            uid=uid,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            start_time=start_time,
            user_repo=self.user_repo,
            response_formatter=self.response_formatter,
            audit_func=self.audit_func,
            text=text,
        )
