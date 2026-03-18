"""Settings command handlers (/debug, /settings)."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

from app.adapters.telegram.command_handlers.decorators import combined_handler
from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )
    from app.config import AppConfig
    from app.core.verbosity import VerbosityResolver

logger = get_logger(__name__)

_DIGEST_WEB_PATH = "/web/digest"


class _UserPrefs(TypedDict, total=False):
    verbosity: str


class SettingsHandler:
    """Handles user-facing settings commands."""

    def __init__(
        self,
        verbosity_resolver: VerbosityResolver | None,
        cfg: AppConfig | None = None,
    ) -> None:
        self._verbosity_resolver = verbosity_resolver
        self._cfg = cfg

    @combined_handler("command_debug", "debug_toggle")
    async def handle_debug(self, ctx: CommandExecutionContext) -> None:
        """Toggle verbosity between reader and debug mode."""
        user = await ctx.user_repo.async_get_user_by_telegram_id(ctx.uid)
        raw_prefs = (user or {}).get("preferences_json") or {}
        prefs: _UserPrefs = cast("_UserPrefs", raw_prefs) if isinstance(raw_prefs, dict) else {}

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

    @combined_handler("command_settings", "settings_open")
    async def handle_settings(self, ctx: CommandExecutionContext) -> None:
        """Open Digest Mini App via inline keyboard button."""
        api_base = ""
        if self._cfg is not None:
            api_base = getattr(self._cfg.telegram, "api_base_url", "") or ""

        if not api_base:
            await ctx.response_formatter.safe_reply(
                ctx.message,
                "API base URL not configured. Set `API_BASE_URL` in your environment.",
            )
            return

        from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

        url = f"{api_base.rstrip('/')}{_DIGEST_WEB_PATH}"
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Digest Settings", web_app=WebAppInfo(url=url))]]
        )

        await ctx.response_formatter.safe_reply(
            ctx.message,
            "Tap the button below to manage your digest settings.",
            reply_markup=keyboard,
        )
