"""Settings command handlers (/debug)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.adapters.telegram.command_handlers.decorators import combined_handler

if TYPE_CHECKING:
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )
    from app.core.verbosity import VerbosityResolver

logger = logging.getLogger(__name__)


class SettingsHandlerImpl:
    """Handles user-facing settings commands."""

    def __init__(self, verbosity_resolver: VerbosityResolver | None) -> None:
        self._verbosity_resolver = verbosity_resolver

    @combined_handler("command_debug", "debug_toggle")
    async def handle_debug(self, ctx: CommandExecutionContext) -> None:
        """Toggle verbosity between reader and debug mode."""
        user = await ctx.user_repo.async_get_user_by_telegram_id(ctx.uid)
        prefs = (user or {}).get("preferences_json") or {}
        if not isinstance(prefs, dict):
            prefs = {}

        current = prefs.get("verbosity", "reader")
        new = "debug" if current == "reader" else "reader"

        await ctx.user_repo.async_update_user_preferences(ctx.uid, {**prefs, "verbosity": new})

        if self._verbosity_resolver is not None:
            self._verbosity_resolver.invalidate_cache(ctx.uid)

        if new == "debug":
            text = (
                "Verbosity: Debug\n"
                "Technical details will appear in notifications.\n"
                "Use /debug to switch back."
            )
        else:
            text = (
                "Verbosity: Reader\n"
                "Notifications will show clean progress.\n"
                "Use /debug for technical details."
            )
        await ctx.response_formatter.safe_reply(ctx.message, text)
