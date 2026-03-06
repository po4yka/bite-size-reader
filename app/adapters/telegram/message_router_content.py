"""Content routing for Telegram messages."""
# mypy: disable-error-code=attr-defined

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from app.adapters.telegram.message_router_helpers import (
    handle_document_file,
    is_txt_file_with_urls,
)
from app.core.ui_strings import t
from app.core.url_utils import looks_like_url
from app.db.user_interactions import async_safe_update_user_interaction

logger = logging.getLogger("app.adapters.telegram.message_router")

_LOCAL_SEARCH_ALIASES: tuple[str, ...] = ("/finddb", "/findlocal")
_ONLINE_SEARCH_ALIASES: tuple[str, ...] = ("/findweb", "/findonline", "/find")

_PRE_ALIAS_UID_COMMANDS: tuple[tuple[str, str], ...] = (
    ("/start", "handle_start_command"),
    ("/help", "handle_help_command"),
    ("/dbinfo", "handle_dbinfo_command"),
    ("/dbverify", "handle_dbverify_command"),
    ("/clearcache", "handle_clearcache_command"),
)
_PRE_SUMMARIZE_TEXT_COMMANDS: tuple[tuple[str, str], ...] = (
    ("/summarize_all", "handle_summarize_all_command"),
)
_POST_SUMMARIZE_UID_COMMANDS: tuple[tuple[str, str], ...] = (("/cancel", "handle_cancel_command"),)
_POST_SUMMARIZE_TEXT_COMMANDS: tuple[tuple[str, str], ...] = (
    ("/unread", "handle_unread_command"),
    ("/read", "handle_read_command"),
    ("/search", "handle_search_command"),
    ("/sync_karakeep", "handle_sync_karakeep_command"),
    ("/cdigest", "handle_cdigest_command"),
    ("/digest", "handle_digest_command"),
    ("/channels", "handle_channels_command"),
    ("/subscribe", "handle_subscribe_command"),
    ("/unsubscribe", "handle_unsubscribe_command"),
    ("/init_session", "handle_init_session_command"),
    ("/settings", "handle_settings_command"),
)
_TAIL_UID_COMMANDS: tuple[tuple[str, str], ...] = (("/debug", "handle_debug_command"),)


class MessageRouterContentMixin:
    """Command/content dispatch for MessageRouter."""

    # Explicit host contract for MessageRouter composition.
    _lang: str
    _should_handle_attachment: Callable[..., bool]
    attachment_processor: Any
    command_processor: Any
    forward_processor: Any
    response_formatter: Any
    url_handler: Any
    user_repo: Any

    async def _route_message_content(
        self,
        message: Any,
        text: str,
        uid: int,
        has_forward: bool,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Route message to appropriate handler based on content."""
        if getattr(message, "contact", None) and self.command_processor.has_active_init_session(
            uid
        ):
            await self.command_processor.handle_init_session_contact(message)
            return

        if getattr(
            message, "web_app_data", None
        ) and self.command_processor.has_active_init_session(uid):
            await self.command_processor.handle_init_session_webapp(message)
            return

        if await self._route_command_message(
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return

        if has_forward and await self._route_forward_message(
            message,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return

        if await self.url_handler.is_awaiting_url(uid) and looks_like_url(text):
            await self.url_handler.handle_awaited_url(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        if text and looks_like_url(text):
            await self.url_handler.handle_direct_url(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        if is_txt_file_with_urls(message):
            await handle_document_file(self, message, correlation_id, interaction_id, start_time)
            return

        if self.attachment_processor and self._should_handle_attachment(message):
            await self.attachment_processor.handle_attachment_flow(
                message, correlation_id=correlation_id, interaction_id=interaction_id
            )
            return

        await self.response_formatter.safe_reply(message, t("fallback_prompt", self._lang))
        logger.debug(
            "unknown_input",
            extra={
                "has_forward": bool(getattr(message, "forward_from_chat", None)),
                "text_len": len(text),
            },
        )
        if interaction_id:
            await async_safe_update_user_interaction(
                self.user_repo,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="unknown_input",
                start_time=start_time,
                logger_=logger,
            )

    async def _route_command_message(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        """Route command message. Returns True when command was handled."""
        route_probe = await self._resolve_command_route_probe(
            text=text,
            uid=uid,
            correlation_id=correlation_id,
        )
        return await self._dispatch_command_route(
            message=message,
            text=text,
            route_probe=route_probe,
            uid=uid,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            start_time=start_time,
        )

    @staticmethod
    def _match_prefix(text: str, prefixes: tuple[str, ...]) -> str | None:
        for prefix in prefixes:
            if text.startswith(prefix):
                return prefix
        return None

    async def _resolve_command_route_probe(
        self,
        *,
        text: str,
        uid: int,
        correlation_id: str,
    ) -> str:
        runtime_runner = getattr(self, "telegram_runtime_runner", None)
        if runtime_runner is None:
            logger.error(
                "m6_telegram_runtime_runner_missing",
                extra={"cid": correlation_id, "uid": uid},
            )
            msg = (
                "Telegram runtime runner is required; "
                "legacy interface-router fallback is decommissioned."
            )
            raise RuntimeError(msg)

        decision = await runtime_runner.resolve_command_route(
            text=text,
            correlation_id=correlation_id,
            actor_key=str(uid),
        )
        if decision.handled and decision.command:
            return decision.command
        return text

    async def _dispatch_uid_command(
        self,
        route_probe: str,
        handlers: tuple[tuple[str, str], ...],
        message: Any,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        for prefix, handler_name in handlers:
            if route_probe.startswith(prefix):
                handler = getattr(self.command_processor, handler_name)
                await handler(message, uid, correlation_id, interaction_id, start_time)
                return True
        return False

    async def _dispatch_text_command(
        self,
        route_probe: str,
        handlers: tuple[tuple[str, str], ...],
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        for prefix, handler_name in handlers:
            if route_probe.startswith(prefix):
                handler = getattr(self.command_processor, handler_name)
                await handler(message, text, uid, correlation_id, interaction_id, start_time)
                return True
        return False

    async def _dispatch_alias_command(
        self,
        route_probe: str,
        aliases: tuple[str, ...],
        handler_name: str,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        matched_alias = self._match_prefix(route_probe, aliases)
        if matched_alias is None:
            return False

        original_alias = self._match_prefix(text, aliases)
        handler = getattr(self.command_processor, handler_name)
        await handler(
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
            command=original_alias or matched_alias,
        )
        return True

    async def _dispatch_summarize_command(
        self,
        route_probe: str,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        if not route_probe.startswith("/summarize"):
            return False

        action, _should_continue = await self.command_processor.handle_summarize_command(
            message, text, uid, correlation_id, interaction_id, start_time
        )
        if action == "awaiting_url":
            await self.url_handler.add_awaiting_user(uid)
        return True

    async def _dispatch_command_route(
        self,
        *,
        message: Any,
        text: str,
        route_probe: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        if await self._dispatch_uid_command(
            route_probe,
            _PRE_ALIAS_UID_COMMANDS,
            message,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return True

        if await self._dispatch_alias_command(
            route_probe,
            _LOCAL_SEARCH_ALIASES,
            "handle_find_local_command",
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return True

        if await self._dispatch_alias_command(
            route_probe,
            _ONLINE_SEARCH_ALIASES,
            "handle_find_online_command",
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return True

        if await self._dispatch_text_command(
            route_probe,
            _PRE_SUMMARIZE_TEXT_COMMANDS,
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return True

        if await self._dispatch_summarize_command(
            route_probe,
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return True

        if await self._dispatch_uid_command(
            route_probe,
            _POST_SUMMARIZE_UID_COMMANDS,
            message,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return True

        if await self._dispatch_text_command(
            route_probe,
            _POST_SUMMARIZE_TEXT_COMMANDS,
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return True

        return await self._dispatch_uid_command(
            route_probe,
            _TAIL_UID_COMMANDS,
            message,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        )

    async def _route_forward_message(
        self,
        message: Any,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        """Route forwarded message. Returns True when handled."""
        fwd_chat = getattr(message, "forward_from_chat", None)
        fwd_msg_id = getattr(message, "forward_from_message_id", None)
        fwd_from_user = getattr(message, "forward_from", None)
        fwd_sender_name = getattr(message, "forward_sender_name", None)

        if fwd_chat is not None and fwd_msg_id is not None:
            await self.forward_processor.handle_forward_flow(
                message, correlation_id=correlation_id, interaction_id=interaction_id
            )
            return True

        if fwd_from_user is not None or fwd_sender_name:
            fwd_text = (
                getattr(message, "text", None) or getattr(message, "caption", None) or ""
            ).strip()
            if fwd_text:
                await self.forward_processor.handle_forward_flow(
                    message, correlation_id=correlation_id, interaction_id=interaction_id
                )
                return True
            if self.attachment_processor and self._should_handle_attachment(message):
                await self.attachment_processor.handle_attachment_flow(
                    message, correlation_id=correlation_id, interaction_id=interaction_id
                )
                return True
            logger.info(
                "forward_skipped_no_text",
                extra={
                    "cid": correlation_id,
                    "has_fwd_user": fwd_from_user is not None,
                    "has_fwd_sender_name": bool(fwd_sender_name),
                },
            )
            await self.response_formatter.safe_reply(
                message,
                "This forwarded message has no text content to summarize. "
                "Please forward a message that contains text.",
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.user_repo,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="forward_no_text",
                    start_time=start_time,
                    logger_=logger,
                )
            return True

        fwd_text = (
            getattr(message, "text", None) or getattr(message, "caption", None) or ""
        ).strip()
        if fwd_text:
            await self.forward_processor.handle_forward_flow(
                message, correlation_id=correlation_id, interaction_id=interaction_id
            )
            return True

        if self.attachment_processor and self._should_handle_attachment(message):
            await self.attachment_processor.handle_attachment_flow(
                message, correlation_id=correlation_id, interaction_id=interaction_id
            )
            return True

        logger.info(
            "forward_skipped_unrecognized",
            extra={
                "cid": correlation_id,
                "has_forward_date": getattr(message, "forward_date", None) is not None,
            },
        )
        await self.response_formatter.safe_reply(
            message,
            "This forwarded message has no text content to summarize. "
            "Please forward a message that contains text.",
        )
        if interaction_id:
            await async_safe_update_user_interaction(
                self.user_repo,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="forward_no_text",
                start_time=start_time,
                logger_=logger,
            )
        return True
