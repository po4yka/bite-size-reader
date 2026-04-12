"""Command handler for explicit mixed-source aggregation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.telegram.command_handlers.decorators import audit_command

if TYPE_CHECKING:
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )
    from app.adapters.telegram.multi_source_aggregation_handler import (
        MultiSourceAggregationHandler,
    )


class AggregationCommandsHandler:
    """Handle `/aggregate` Telegram commands."""

    def __init__(self, aggregation_handler: MultiSourceAggregationHandler) -> None:
        self._aggregation_handler = aggregation_handler

    @audit_command("command_aggregate", include_text=True)
    async def handle_aggregate(self, ctx: CommandExecutionContext) -> tuple[str | None, bool]:
        await self._aggregation_handler.handle_command(
            message=ctx.message,
            text=ctx.text,
            uid=ctx.uid,
            correlation_id=ctx.correlation_id,
            interaction_id=ctx.interaction_id,
        )
        return None, False
