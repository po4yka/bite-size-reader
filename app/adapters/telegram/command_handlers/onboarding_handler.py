"""Onboarding command handlers (/start, /help).

This module handles the simplest commands that introduce users to the bot
and provide help information.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.adapters.telegram.command_handlers.decorators import audit_command, track_interaction

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )

logger = logging.getLogger(__name__)


class OnboardingHandlerImpl:
    """Implementation of onboarding commands (/start, /help).

    These are the simplest commands with minimal logic - they just
    delegate to the response formatter to send welcome/help messages.
    """

    def __init__(self, response_formatter: ResponseFormatter) -> None:
        """Initialize the onboarding handler.

        Args:
            response_formatter: The response formatter for sending messages.
        """
        self._formatter = response_formatter

    @audit_command("command_start")
    @track_interaction("welcome")
    async def handle_start(self, ctx: CommandExecutionContext) -> None:
        """Handle /start command.

        Sends a welcome message to the user introducing the bot's capabilities.

        Args:
            ctx: The command execution context.
        """
        await self._formatter.send_welcome(ctx.message)

    @audit_command("command_help")
    @track_interaction("help")
    async def handle_help(self, ctx: CommandExecutionContext) -> None:
        """Handle /help command.

        Sends help information with available commands and usage instructions.

        Args:
            ctx: The command execution context.
        """
        await self._formatter.send_help(ctx.message)
